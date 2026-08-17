import io
import zipfile

import httpx
import numpy as np
import pytest
from pydantic_ai.models.function import FunctionModel

import ragbot.api.jobs as jobs_module
import ragbot.core.Repository as repository_module
from ragbot.api.main import app
from ragbot.api.state import AppState

REPO_URL = 'https://codeload.github.com/testowner/testrepo/zip/refs/heads/main'
REPO_KEY = 'testowner_testrepo_main'


def _build_fake_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('testrepo-main/README.md', '# Test repo\n\nA tiny fixture repo.\n')
        zf.writestr(
            'testrepo-main/src/app.py',
            "def hybrid_search():\n    return 'combines keyword and vector results'\n",
        )
    return buf.getvalue()


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code


class FakeEmbedder:
    name = 'fake:test-embedder'

    def encode(self, texts):
        if isinstance(texts, str):
            return self._vector(texts)
        return np.array([self._vector(t) for t in texts])

    @staticmethod
    def _vector(text):
        rng = np.random.default_rng(abs(hash(text)) % (2 ** 32))
        return rng.random(8)


@pytest.fixture(autouse=True)
def fake_network(monkeypatch):
    """No real download and no real embedding API calls in this file."""
    zip_bytes = _build_fake_zip()
    monkeypatch.setattr(repository_module.requests, 'get', lambda url: FakeResponse(zip_bytes))
    monkeypatch.setattr(jobs_module, 'get_embedder', lambda: FakeEmbedder())


@pytest.fixture
async def client():
    app.state.ragbot = AppState()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as c:
        yield c


async def _ingest(client, search_method='TEXT', chunking_strategy='AUTO'):
    resp = await client.post('/api/repos', json={
        'repo_url': REPO_URL, 'chunking_strategy': chunking_strategy, 'search_method': search_method,
    })
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body['repo_key'] == REPO_KEY

    # With httpx's ASGITransport, BackgroundTasks run to completion before the
    # request coroutine returns, but poll anyway so this test doesn't depend on
    # that Starlette implementation detail.
    for _ in range(50):
        job = (await client.get(f"/api/jobs/{body['job_id']}")).json()
        if job['status'] in ('succeeded', 'failed'):
            break
    assert job['status'] == 'succeeded', job
    return body['job_id'], body['repo_key']


class TestMeta:

    async def test_health(self, client):
        resp = await client.get('/api/health')
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'ok'
        assert 'chat_model' in body and 'embedder' in body

    async def test_config_exposes_labels_not_just_names(self, client):
        resp = await client.get('/api/config')
        body = resp.json()

        assert {o['name'] for o in body['chunking_strategies']} == {
            'AUTO', 'AST', 'MARKDOWN', 'PARAGRAPH', 'CHARACTER', 'LLM',
        }
        assert all(o['label'] for o in body['chunking_strategies'])
        assert {o['name'] for o in body['search_methods']} == {'TEXT', 'VECTOR', 'HYBRID'}
        assert all(o['label'] for o in body['search_methods'])


class TestIngestionLifecycle:

    async def test_ingest_job_reaches_succeeded_with_phases(self, client):
        resp = await client.post('/api/repos', json={'repo_url': REPO_URL, 'chunking_strategy': 'AUTO', 'search_method': 'TEXT'})
        job_id = resp.json()['job_id']

        job = (await client.get(f'/api/jobs/{job_id}')).json()
        assert job['status'] in ('pending', 'running', 'succeeded')

        for _ in range(50):
            job = (await client.get(f'/api/jobs/{job_id}')).json()
            if job['status'] == 'succeeded':
                break
        assert job['status'] == 'succeeded'
        assert job['phase'] == 'ready'
        assert job['result']['repo_key'] == REPO_KEY

    async def test_unknown_job_is_404(self, client):
        resp = await client.get('/api/jobs/does-not-exist')
        assert resp.status_code == 404

    async def test_invalid_chunking_strategy_is_422(self, client):
        resp = await client.post('/api/repos', json={'repo_url': REPO_URL, 'chunking_strategy': 'NOPE', 'search_method': 'TEXT'})
        assert resp.status_code == 422

    async def test_job_events_stream_emits_status_events(self, client):
        resp = await client.post('/api/repos', json={'repo_url': REPO_URL, 'chunking_strategy': 'AUTO', 'search_method': 'TEXT'})
        job_id = resp.json()['job_id']

        async with client.stream('GET', f'/api/jobs/{job_id}/events') as stream:
            chunks = []
            async for line in stream.aiter_lines():
                chunks.append(line)
                if 'succeeded' in line:
                    break

        text = '\n'.join(chunks)
        assert 'event: status' in text
        assert 'succeeded' in text

    async def test_repo_appears_in_listing_after_ingest(self, client):
        await _ingest(client)

        resp = await client.get('/api/repos')
        keys = [r['repo_key'] for r in resp.json()]
        assert REPO_KEY in keys

    async def test_repo_detail_has_language_stats_and_chunk_count(self, client):
        await _ingest(client)

        resp = await client.get(f'/api/repos/{REPO_KEY}')
        body = resp.json()
        assert body['indexed'] is True
        assert body['chunk_count'] > 0
        assert body['language_stats']
        assert body['chunking_strategy'] == 'AUTO'
        assert body['search_method'] == 'TEXT'

    async def test_unknown_repo_is_404(self, client):
        resp = await client.get('/api/repos/does-not-exist')
        assert resp.status_code == 404


class TestFiles:

    async def test_file_tree_lists_ingested_files(self, client):
        await _ingest(client)

        resp = await client.get(f'/api/repos/{REPO_KEY}/files')
        body = resp.json()
        paths = _flatten_paths(body['root'])
        assert 'README.md' in paths
        assert 'src/app.py' in paths

    async def test_file_content_returns_lines(self, client):
        await _ingest(client)

        resp = await client.get(f'/api/repos/{REPO_KEY}/files/src/app.py')
        body = resp.json()
        assert 'hybrid_search' in body['content']
        assert body['start_line'] == 1

    async def test_file_content_respects_line_range(self, client):
        await _ingest(client)

        resp = await client.get(f'/api/repos/{REPO_KEY}/files/src/app.py', params={'start_line': 2, 'end_line': 2})
        body = resp.json()
        assert body['start_line'] == 2 and body['end_line'] == 2
        assert 'def hybrid_search' not in body['content']

    async def test_missing_file_is_404(self, client):
        await _ingest(client)

        resp = await client.get(f'/api/repos/{REPO_KEY}/files/nope.py')
        assert resp.status_code == 404

    @pytest.mark.parametrize('evil', ['../../etc/passwd', '..%2f..%2fsecret.txt'])
    async def test_path_traversal_is_rejected(self, client, evil):
        await _ingest(client)

        resp = await client.get(f'/api/repos/{REPO_KEY}/files/{evil}')
        assert resp.status_code in (400, 404)


def _flatten_paths(nodes):
    out = []
    for node in nodes:
        if node['type'] == 'file':
            out.append(node['path'])
        out.extend(_flatten_paths(node['children']))
    return out


class TestRepoDeletion:

    async def test_delete_evicts_repo(self, client):
        await _ingest(client)

        resp = await client.delete(f'/api/repos/{REPO_KEY}')
        assert resp.status_code == 204

        resp = await client.get(f'/api/repos/{REPO_KEY}')
        assert resp.status_code == 404

    async def test_deleting_unknown_repo_is_404(self, client):
        resp = await client.delete('/api/repos/does-not-exist')
        assert resp.status_code == 404


class TestConversations:

    async def test_create_conversation_requires_ingested_repo(self, client):
        resp = await client.post('/api/conversations', json={'repo_key': 'does-not-exist'})
        assert resp.status_code == 404

    async def test_create_and_fetch_conversation(self, client):
        await _ingest(client)

        resp = await client.post('/api/conversations', json={'repo_key': REPO_KEY})
        assert resp.status_code == 201
        conv_id = resp.json()['conversation_id']

        resp = await client.get(f'/api/conversations/{conv_id}')
        body = resp.json()
        assert body['repo_key'] == REPO_KEY
        assert body['messages'] == []

    async def test_ask_streams_tokens_and_citation_and_persists_history(self, client, monkeypatch):
        await _ingest(client)
        conv_id = (await client.post('/api/conversations', json={'repo_key': REPO_KEY})).json()['conversation_id']

        async def stream_function(messages, agent_info):
            yield "hybrid_search lives at src/app.py:1-2."

        built = app.state.ragbot.get_or_build_index(REPO_KEY)
        built.agent_wrapper.agent.model = FunctionModel(stream_function=stream_function)

        events = []
        async with client.stream(
            'POST', f'/api/conversations/{conv_id}/messages', json={'content': 'Where does hybrid_search live?'},
        ) as stream:
            async for line in stream.aiter_lines():
                if line.startswith('event:'):
                    events.append(line.split(':', 1)[1].strip())

        assert 'token' in events
        assert 'citation' in events
        assert events[-1] == 'done'

        detail = (await client.get(f'/api/conversations/{conv_id}')).json()
        assert len(detail['messages']) == 2
        assert detail['messages'][0]['role'] == 'user'
        assert detail['messages'][1]['role'] == 'assistant'
        assert 'hybrid_search' in detail['messages'][1]['content']

    async def test_clear_conversation_resets_messages(self, client):
        await _ingest(client)
        conv_id = (await client.post('/api/conversations', json={'repo_key': REPO_KEY})).json()['conversation_id']

        resp = await client.delete(f'/api/conversations/{conv_id}')
        assert resp.status_code == 204

        detail = (await client.get(f'/api/conversations/{conv_id}')).json()
        assert detail['messages'] == []

    async def test_unknown_conversation_is_404(self, client):
        resp = await client.get('/api/conversations/does-not-exist')
        assert resp.status_code == 404

    async def test_ask_on_unknown_conversation_is_404(self, client):
        resp = await client.post('/api/conversations/does-not-exist/messages', json={'content': 'hi'})
        assert resp.status_code == 404
