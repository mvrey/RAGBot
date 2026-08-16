"""Command-line entry point.

A thin wrapper over the same pipeline the Streamlit app uses, for asking one-off
questions or evaluating an answer without opening a browser.

    python main.py --repo <codeload-zip-url> --question "How does search work?"
    python main.py --question "..." --cached --evaluate
"""

import argparse
import asyncio
import json

from src.Repository import Repository
from src.ChunkingStrategy import ChunkingStrategy
from src.SearchStrategy import SearchStrategy, SearchStrategyType
from src.Embeddings import get_embedder
from src.AgentWrapper import AgentWrapper
from src.AgentLog import AgentLog
from src.Prompts import Prompts

DEFAULT_REPO = 'https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main'


def build_agent(repo_url: str, use_cache: bool, search_method: SearchStrategyType):
    repository = Repository(repo_url)

    if use_cache:
        files = repository.load_cached_repo_files()
        print(f"Loaded {len(files)} files from cache")
    else:
        files = repository.get_repo_files()
        print(f"Downloaded {len(files)} files")
    print(f"Languages: {repository.language_stats()}")

    chunks = repository.chunk(ChunkingStrategy.AUTO)
    print(f"Created {len(chunks)} chunks")

    embedder = get_embedder()
    print(f"Indexing with {embedder.name}")

    agent_wrapper = AgentWrapper(
        chunks,
        search_strategy=SearchStrategy(embedder=embedder),
        search_method=search_method,
        repo_dir=repository.repo_dir,
    )
    agent_wrapper.setup(Prompts.system_prompt_for(repository.blob_url_base()))
    return agent_wrapper


async def evaluate(agent_log: AgentLog, log_record):
    """Score the most recent answer with the LLM-as-judge checklist."""
    from pydantic_ai import Agent
    from src.EvaluationCheck import EvaluationChecklist

    eval_agent = Agent(
        name='eval_agent',
        model='gpt-4.1-nano',
        instructions=Prompts.EVALUATION_PROMPT,
        output_type=EvaluationChecklist,
    )
    return await agent_log.evaluate_log_record(eval_agent, log_record)


def main():
    parser = argparse.ArgumentParser(description="Ask questions about a GitHub repository.")
    parser.add_argument('--repo', default=DEFAULT_REPO, help="codeload.github.com zip URL")
    parser.add_argument('--question', default=Prompts.USER_PROMPT)
    parser.add_argument('--cached', action='store_true', help="load from disk instead of downloading")
    parser.add_argument('--evaluate', action='store_true', help="score the answer afterwards")
    parser.add_argument(
        '--search',
        default=SearchStrategyType.HYBRID.name,
        choices=[s.name for s in SearchStrategyType],
    )
    args = parser.parse_args()

    agent_wrapper = build_agent(args.repo, args.cached, SearchStrategyType[args.search])

    print(f"\nQuestion: {args.question}\n")
    result = asyncio.run(agent_wrapper.run(args.question))
    print(result['response'])

    agent_log = AgentLog()
    log_path = agent_log.log_interaction_to_file(
        agent_wrapper.agent, result['conversation'], source='cli'
    )
    print(f"\nLogged to {log_path}")

    if args.evaluate:
        log_record = agent_log.load_log_file(log_path)
        evaluation = asyncio.run(evaluate(agent_log, log_record))
        print(f"\nEvaluation: {evaluation.summary}")
        for check in evaluation.checklist:
            status = "PASS" if check.check_pass else "FAIL"
            print(f"  [{status}] {check.check_name}: {check.justification}")


if __name__ == '__main__':
    main()
