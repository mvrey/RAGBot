import pytest
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from ragbot.core.AgentWrapper import AgentWrapper
from ragbot.core.SearchStrategy import SearchStrategy, SearchStrategyType
from ragbot.core.TextSearcher import TextSearcher

CHUNKS = [
    {
        'chunk': 'def hybrid_search(): combine keyword and vector results with RRF',
        'body': 'def hybrid_search(): combine keyword and vector results with RRF',
        'filename': 'src/TextSearcher.py',
        'symbol': 'hybrid_search',
        'start_line': 59,
        'end_line': 72,
        'language': 'python',
    }
]


def _text_only_search_strategy():
    """A SearchStrategy that never needs an embedder, for TEXT-only search."""
    strategy = SearchStrategy.__new__(SearchStrategy)
    searcher = TextSearcher.__new__(TextSearcher)
    searcher._text_index = None
    searcher._vector_index = None
    searcher._embedder = None
    strategy.searcher = searcher
    return strategy


def _make_wrapper(model):
    """An AgentWrapper wired to a fake FunctionModel - no network, no API key."""
    return AgentWrapper(
        CHUNKS,
        model=model,
        search_strategy=_text_only_search_strategy(),
        search_method=SearchStrategyType.TEXT,
    )


class TestRunStreamEvents:

    async def test_stream_includes_tool_call_and_result(self):
        calls = {'n': 0}

        async def stream_function(messages, agent_info: AgentInfo):
            calls['n'] += 1
            if calls['n'] == 1:
                yield {0: DeltaToolCall(name='search_code', json_args='{"query": "hybrid_search"}')}
            else:
                for chunk in ["The ", "hybrid_search ", "function combines results. "]:
                    yield chunk

        wrapper = _make_wrapper(FunctionModel(stream_function=stream_function))
        wrapper.setup("test instructions")

        events = [event async for event in wrapper.run_stream("How does hybrid search work?")]
        kinds = [e['event'] for e in events]

        assert 'tool_call' in kinds
        assert 'tool_result' in kinds
        assert kinds.count('token') == 3
        assert kinds[-1] == 'done'

        tool_call = events[kinds.index('tool_call')]
        assert tool_call['data']['tool'] == 'search_code'
        assert tool_call['data']['args'] == {'query': 'hybrid_search'}

        tool_result = events[kinds.index('tool_result')]
        assert tool_result['data']['tool'] == 'search_code'
        assert 'hybrid_search' in tool_result['data']['summary']

    async def test_stream_tokens_concatenate_to_full_answer(self):
        async def stream_function(messages, agent_info: AgentInfo):
            for chunk in ["Hel", "lo, ", "world."]:
                yield chunk

        wrapper = _make_wrapper(FunctionModel(stream_function=stream_function))
        wrapper.setup("test instructions")

        events = [event async for event in wrapper.run_stream("hi")]
        tokens = [e['data']['delta'] for e in events if e['event'] == 'token']

        assert ''.join(tokens) == "Hello, world."

    async def test_citations_are_parsed_from_final_text(self):
        async def stream_function(messages, agent_info: AgentInfo):
            yield "See src/TextSearcher.py:59-72 for the implementation."

        wrapper = _make_wrapper(FunctionModel(stream_function=stream_function))
        wrapper.setup("test instructions")

        events = [event async for event in wrapper.run_stream("cite it")]
        citations = [e['data'] for e in events if e['event'] == 'citation']

        assert citations == [{'path': 'src/TextSearcher.py', 'start': 59, 'end': 72}]

    async def test_duplicate_citations_are_not_repeated(self):
        async def stream_function(messages, agent_info: AgentInfo):
            yield "src/TextSearcher.py:59-72 and again src/TextSearcher.py:59-72."

        wrapper = _make_wrapper(FunctionModel(stream_function=stream_function))
        wrapper.setup("test instructions")

        events = [event async for event in wrapper.run_stream("cite it twice")]
        citations = [e['data'] for e in events if e['event'] == 'citation']

        assert len(citations) == 1

    async def test_done_event_carries_usage(self):
        async def stream_function(messages, agent_info: AgentInfo):
            yield "done."

        wrapper = _make_wrapper(FunctionModel(stream_function=stream_function))
        wrapper.setup("test instructions")

        events = [event async for event in wrapper.run_stream("hi")]
        done = events[-1]

        assert done['event'] == 'done'
        assert 'message_id' in done['data']
        assert set(done['data']['usage']) == {'input_tokens', 'output_tokens', 'requests'}

    async def test_history_sink_receives_updated_history(self):
        async def stream_function(messages, agent_info: AgentInfo):
            yield "hi there"

        wrapper = _make_wrapper(FunctionModel(stream_function=stream_function))
        wrapper.setup("test instructions")

        sink = []
        events = [event async for event in wrapper.run_stream("hi", history_sink=sink)]

        assert events[-1]['event'] == 'done'
        assert len(sink) == 1
        assert sink[0]  # a non-empty message history, usable as the next call's message_history

    async def test_history_sink_not_touched_without_arg(self):
        async def stream_function(messages, agent_info: AgentInfo):
            yield "hi there"

        wrapper = _make_wrapper(FunctionModel(stream_function=stream_function))
        wrapper.setup("test instructions")

        # Should not raise even though no sink was passed.
        events = [event async for event in wrapper.run_stream("hi")]
        assert events[-1]['event'] == 'done'

    async def test_run_stream_requires_setup(self):
        wrapper = _make_wrapper(FunctionModel(stream_function=lambda messages, agent_info: None))

        with pytest.raises(ValueError, match='not initialized'):
            async for _ in wrapper.run_stream("hi"):
                pass
