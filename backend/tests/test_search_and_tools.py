import numpy as np
import pytest

from ragbot.core.AgentWrapper import AgentWrapper, MAX_FILE_LINES
from ragbot.core.SearchStrategy import SearchStrategy, SearchStrategyType
from ragbot.core.TextSearcher import TextSearcher


class FakeEmbedder:
    """Deterministic stand-in so search tests need no model download or API call."""

    name = 'fake'

    def __init__(self):
        self.calls = 0

    def encode(self, texts, on_progress=None):
        if isinstance(texts, str):
            return self._vector(texts)
        self.calls += 1
        vectors = [self._vector(t) for t in texts]
        if on_progress:
            on_progress(len(vectors), len(vectors))
        return np.array(vectors)

    @staticmethod
    def _vector(text):
        lowered = text.lower()
        # Three crude topic axes are enough to make ranking assertions meaningful.
        return np.array([
            lowered.count('search'),
            lowered.count('embed'),
            lowered.count('banana'),
        ], dtype=float) + 0.01


CHUNKS = [
    {'chunk': 'def hybrid_search(): combine search results', 'body': 'b1',
     'filename': 'search.py', 'symbol': 'hybrid_search', 'start_line': 1, 'end_line': 5},
    {'chunk': 'def embed_text(): embed embed the text', 'body': 'b2',
     'filename': 'embed.py', 'symbol': 'embed_text', 'start_line': 1, 'end_line': 4},
    {'chunk': 'banana banana potassium fruit', 'body': 'b3',
     'filename': 'fruit.py', 'symbol': 'banana', 'start_line': 1, 'end_line': 2},
]


class TestSearch:

    def test_vector_search_returns_results(self):
        searcher = TextSearcher(embedder=FakeEmbedder())

        results = searcher.vector_search('search', CHUNKS, num_results=2)

        # Regression: vector_search used to compute the query vector and return None.
        assert results
        assert results[0]['filename'] == 'search.py'

    def test_vector_index_is_built_once(self):
        embedder = FakeEmbedder()
        searcher = TextSearcher(embedder=embedder)

        searcher.vector_search('search', CHUNKS)
        searcher.vector_search('banana', CHUNKS)

        assert embedder.calls == 1, "corpus should be embedded once, not per query"

    def test_text_search_matches_symbols(self):
        searcher = TextSearcher(embedder=FakeEmbedder())

        results = searcher.text_search('hybrid_search', CHUNKS, num_results=1)

        assert results[0]['symbol'] == 'hybrid_search'

    def test_hybrid_search_deduplicates(self):
        searcher = TextSearcher(embedder=FakeEmbedder())

        results = searcher.hybrid_search('search', CHUNKS, num_results=5)

        keys = [(r['filename'], r['start_line']) for r in results]
        assert len(keys) == len(set(keys))

    def test_hybrid_search_respects_num_results(self):
        searcher = TextSearcher(embedder=FakeEmbedder())

        assert len(searcher.hybrid_search('search', CHUNKS, num_results=1)) == 1

    def test_rrf_rewards_agreement_between_retrievers(self):
        searcher = TextSearcher(embedder=FakeEmbedder())

        results = searcher.hybrid_search('search', CHUNKS, num_results=3)

        # Both retrievers rank search.py first, so fusion must keep it on top rather
        # than simply concatenating the two result lists.
        assert results[0]['filename'] == 'search.py'

    def test_strategy_dispatch(self):
        strategy = SearchStrategy(embedder=FakeEmbedder())

        for kind in SearchStrategyType:
            assert strategy.execute_strategy(kind, 'search', CHUNKS, num_results=1)

    def test_invalid_strategy_raises(self):
        strategy = SearchStrategy(embedder=FakeEmbedder())

        with pytest.raises(ValueError):
            strategy.execute_strategy("nope", 'search', CHUNKS)


@pytest.fixture
def repo_dir(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 51)), encoding='utf-8'
    )
    (tmp_path / "src" / "big.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 1001)), encoding='utf-8'
    )
    (tmp_path / "README.md").write_text("# Title\n", encoding='utf-8')
    (tmp_path / "secret.txt").write_text("outside", encoding='utf-8')
    return tmp_path


@pytest.fixture
def tools(repo_dir):
    wrapper = AgentWrapper(
        CHUNKS,
        search_strategy=SearchStrategy(embedder=FakeEmbedder()),
        repo_dir=repo_dir,
    )
    return {t.__name__: t for t in wrapper.tools}


class TestAgentTools:

    def test_all_tools_registered_when_repo_dir_present(self, tools):
        assert set(tools) == {'search_code', 'read_file', 'list_files'}

    def test_navigation_tools_absent_without_repo_dir(self):
        wrapper = AgentWrapper(CHUNKS, search_strategy=SearchStrategy(embedder=FakeEmbedder()))

        assert [t.__name__ for t in wrapper.tools] == ['search_code']

    def test_read_file_returns_numbered_lines(self, tools):
        output = tools['read_file']('src/app.py', 2, 4)

        assert 'line 2' in output and 'line 4' in output
        assert 'line 5' not in output

    def test_read_file_truncates_large_reads(self, tools):
        output = tools['read_file']('src/big.py')

        assert 'truncated' in output
        assert len(output.splitlines()) <= MAX_FILE_LINES + 2

    def test_read_file_handles_out_of_range(self, tools):
        assert 'only 50 lines' in tools['read_file']('src/app.py', 999)

    def test_read_file_reports_missing_files(self, tools):
        assert 'not found' in tools['read_file']('nope.py').lower()

    @pytest.mark.parametrize("evil", [
        "../secret.txt",
        "../../etc/passwd",
        "src/../../secret.txt",
    ])
    def test_read_file_blocks_path_traversal(self, tools, evil):
        assert 'not allowed' in tools['read_file'](evil)

    def test_list_files_lists_the_repo(self, tools):
        output = tools['list_files']()

        assert 'src/app.py' in output
        assert 'README.md' in output

    def test_list_files_scopes_to_subdirectory(self, tools):
        output = tools['list_files']('src')

        assert 'src/app.py' in output
        assert 'README.md' not in output

    def test_list_files_blocks_traversal(self, tools):
        assert 'not allowed' in tools['list_files']('../..')

    def test_search_code_formats_citations(self, tools):
        output = tools['search_code']('search')

        assert 'search.py:1-5' in output
        assert 'hybrid_search' in output
