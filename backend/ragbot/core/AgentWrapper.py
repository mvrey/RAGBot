import re
from pathlib import Path
from typing import AsyncIterator, Dict, List

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)

from ragbot.core.LLM import get_model_name
from ragbot.core.SearchStrategy import SearchStrategy, SearchStrategyType

# Caps that keep a single tool call from swallowing the context window.
MAX_FILE_LINES = 400
MAX_LISTED_FILES = 300
DEFAULT_SEARCH_RESULTS = 5

# Matches the citation format the system prompt asks for, e.g. "src/X.py:12-34",
# including inside a markdown link's visible text - [src/X.py:12-34](url).
CITATION_RE = re.compile(r'([\w.\-/]+\.[A-Za-z0-9_]+):(\d+)-(\d+)')

# Tool return content can be long (search_code returns several snippets); the UI
# only needs enough to show what happened, not the full payload.
TOOL_RESULT_SUMMARY_CHARS = 200


class AgentWrapper:

    def __init__(
        self,
        documents: List[Dict],
        agent_name: str = "faq_agent",
        model: str = None,
        search_strategy: SearchStrategy = None,
        search_method: SearchStrategyType = SearchStrategyType.HYBRID,
        repo_dir: Path = None,
        num_results: int = DEFAULT_SEARCH_RESULTS,
    ):
        self.documents = documents
        self.agent_name = agent_name
        self.model = model or get_model_name()
        self.search_strategy = search_strategy or SearchStrategy()
        self.search_method = search_method
        self.repo_dir = Path(repo_dir) if repo_dir else None
        self.num_results = num_results
        self.agent = None

        self.tools = [self._make_search_code()]
        if self.repo_dir:
            # Navigation tools only work off the on-disk cache; without it the agent
            # is limited to retrieved snippets.
            self.tools.extend([self._make_read_file(), self._make_list_files()])


    def _make_search_code(self):
        def search_code(query: str) -> str:
            """Search the repository's code and documentation for relevant snippets.

            Args:
                query: What to look for, in natural language or as a symbol name.
            """
            results = self.search_strategy.execute_strategy(
                self.search_method, query, self.documents, num_results=self.num_results
            )

            if not results:
                return "No relevant information found."

            formatted = []
            for idx, result in enumerate(results, 1):
                filename = result.get('filename', 'unknown file')
                symbol = result.get('symbol') or ''
                start, end = result.get('start_line'), result.get('end_line')
                location = f"{filename}:{start}-{end}" if start else filename
                heading = f"Result {idx} - {location}"
                if symbol:
                    heading += f" ({symbol})"
                body = result.get('body') or result.get('chunk', '')
                formatted.append(f"{heading}\n{body}\n")

            return "\n".join(formatted)

        return search_code


    def _make_read_file(self):
        def read_file(path: str, start_line: int = None, end_line: int = None) -> str:
            """Read a file from the repository, optionally only a range of lines.

            Args:
                path: Repository-relative path, e.g. "src/TextSearcher.py".
                start_line: First line to return (1-based). Omit to start at the top.
                end_line: Last line to return, inclusive. Omit to read to the end.
            """
            try:
                target = self._safe_repo_path(path)
            except ValueError as e:
                return str(e)

            if not target.is_file():
                return f"File not found: {path}"

            lines = target.read_text(encoding='utf-8', errors='ignore').splitlines()
            total = len(lines)

            first = max(start_line or 1, 1)
            last = min(end_line or total, total)
            if first > total:
                return f"{path} has only {total} lines."

            selected = lines[first - 1:last]
            truncated = False
            if len(selected) > MAX_FILE_LINES:
                selected = selected[:MAX_FILE_LINES]
                last = first + MAX_FILE_LINES - 1
                truncated = True

            numbered = "\n".join(
                f"{first + offset:>5}  {line}" for offset, line in enumerate(selected)
            )
            header = f"{path} (lines {first}-{last} of {total})"
            if truncated:
                header += f" [truncated to {MAX_FILE_LINES} lines; request a narrower range for more]"
            return f"{header}\n{numbered}"

        return read_file


    def _make_list_files(self):
        def list_files(subdirectory: str = None) -> str:
            """List the repository's indexed files, optionally under a subdirectory.

            Args:
                subdirectory: Repository-relative directory to list. Omit for the whole repo.
            """
            base = self.repo_dir
            if subdirectory:
                try:
                    base = self._safe_repo_path(subdirectory)
                except ValueError as e:
                    return str(e)
                if not base.is_dir():
                    return f"Not a directory: {subdirectory}"

            paths = sorted(
                p.relative_to(self.repo_dir).as_posix()
                for p in base.rglob('*')
                if p.is_file() and p.name != '_meta.json'
            )

            if not paths:
                return "No files found."

            total = len(paths)
            listing = "\n".join(paths[:MAX_LISTED_FILES])
            if total > MAX_LISTED_FILES:
                listing += f"\n... and {total - MAX_LISTED_FILES} more (narrow with a subdirectory)"
            return f"{total} files:\n{listing}"

        return list_files


    def _safe_repo_path(self, path: str) -> Path:
        return self.safe_repo_path(self.repo_dir, path)


    @staticmethod
    def safe_repo_path(repo_dir: Path, path: str) -> Path:
        """Resolve a path relative to repo_dir, refusing anything outside it.

        Shared by the read_file/list_files tools and the API's file-content
        endpoint - the traversal check must live in exactly one place, since it
        is now reachable by anyone who can call the API, not just the model.
        """
        if repo_dir is None:
            raise ValueError("No repository directory is available.")

        repo_dir = Path(repo_dir)
        candidate = (repo_dir / path).resolve()
        root = repo_dir.resolve()
        if root != candidate and root not in candidate.parents:
            raise ValueError(f"Path outside the repository is not allowed: {path}")
        return candidate


    def setup(self, instructions: str) -> None:
        self.agent = Agent(
            name=self.agent_name,
            instructions=instructions,
            tools=self.tools,
            model=self.model
        )


    async def run(self, prompt: str, message_history=None) -> Dict:
        if not self.agent:
            raise ValueError("Agent not initialized. Call setup() first.")

        result = await self.agent.run(user_prompt=prompt, message_history=message_history)
        return {
            'conversation': result.all_messages(),
            'response': result.output
        }


    async def run_stream(self, prompt: str, message_history=None, *, history_sink: list = None) -> AsyncIterator[Dict]:
        """Run the agent, yielding SSE-shaped events as they happen.

        Uses agent.iter() rather than run_stream(): the latter only exposes text
        tokens, but the UI also needs to show tool calls and results as they
        happen ("what the agent did"), not just the final answer.

        Yields dicts of the form {'event': <type>, 'data': <json-able dict>},
        matching the API's SSE contract (token / tool_call / tool_result /
        citation / done). Raising is left to the caller: an in-flight error
        surfaces as an exception here, and the caller is responsible for turning
        it into an `error` event.

        history_sink: if given, the full updated message history (for the next
        turn's message_history=...) is appended to it once the run completes.
        A return value, not an instance attribute: one AgentWrapper is shared
        across every conversation on the same (repo, chunking, search) index, so
        stashing per-call state on self would let concurrent chats clobber each
        other's history.
        """
        if not self.agent:
            raise ValueError("Agent not initialized. Call setup() first.")

        full_text = ''
        seen_citations = set()

        async with self.agent.iter(user_prompt=prompt, message_history=message_history) as agent_run:
            async for node in agent_run:
                if Agent.is_model_request_node(node):
                    async with node.stream(agent_run.ctx) as request_stream:
                        async for event in request_stream:
                            delta = self._text_delta(event)
                            if delta:
                                full_text += delta
                                yield {'event': 'token', 'data': {'delta': delta}}

                elif Agent.is_call_tools_node(node):
                    async with node.stream(agent_run.ctx) as handle_stream:
                        async for event in handle_stream:
                            if isinstance(event, FunctionToolCallEvent):
                                yield {
                                    'event': 'tool_call',
                                    'data': {'tool': event.part.tool_name, 'args': event.part.args_as_dict()},
                                }
                            elif isinstance(event, FunctionToolResultEvent):
                                yield {
                                    'event': 'tool_result',
                                    'data': self._tool_result_data(event),
                                }

            for match in CITATION_RE.finditer(full_text):
                key = match.groups()
                if key in seen_citations:
                    continue
                seen_citations.add(key)
                path, start, end = key
                yield {
                    'event': 'citation',
                    'data': {'path': path, 'start': int(start), 'end': int(end)},
                }

            result = agent_run.result
            usage = result.usage()
            if history_sink is not None:
                history_sink.append(result.all_messages())
            yield {
                'event': 'done',
                'data': {
                    'message_id': str(len(result.all_messages())),
                    'usage': {
                        'input_tokens': usage.input_tokens,
                        'output_tokens': usage.output_tokens,
                        'requests': usage.requests,
                    },
                },
            }


    @staticmethod
    def _text_delta(event) -> str:
        if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
            return event.part.content
        if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
            return event.delta.content_delta
        return ''


    @staticmethod
    def _tool_result_data(event: FunctionToolResultEvent) -> Dict:
        result = event.result
        tool_name = getattr(result, 'tool_name', '') or ''
        content = getattr(result, 'content', '') or ''
        summary = str(content).replace('\n', ' ').strip()
        if len(summary) > TOOL_RESULT_SUMMARY_CHARS:
            summary = summary[:TOOL_RESULT_SUMMARY_CHARS] + '...'
        return {'tool': tool_name, 'summary': summary}


    def print_results(self, result: Dict) -> None:
        print("Conversation History:")
        for message in result['conversation']:
            print(f"\n{message}")

        print("\nFinal Response:")
        print(result['response'])
