import asyncio
from src.TechnicalDocumentation import TechnicalDocumentation
from src.ChunkingStrategy import ChunkingStrategy
from src.SearchStrategy import SearchStrategy, SearchStrategyType
from src.Prompts import Prompts
from src.AgentWrapper import AgentWrapper
from src.AgentLog import AgentLog


##########################################
# Day 1: Read repo files

#Read repo docs
docs = TechnicalDocumentation('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main')
dtc_fastapi = docs.get_repo_doc_files()

print(f"Repository documents: {len(dtc_fastapi)}")


##########################################
# Day 2: Chunking

chunking_strategy = ChunkingStrategy(ChunkingStrategy.MARKDOWN)
chunking_strategy.chunk(docs)

docs.print_summary()


##########################################
# Day 3: Indexing and searching

search_strategy = SearchStrategy()
results = search_strategy.execute_strategy(SearchStrategyType.HYBRID, Prompts.USER_PROMPT, dtc_fastapi)

print("Search results:\n")
print(results)


##########################################
# Day 4: Agents and tools

agent_wrapper = AgentWrapper(dtc_fastapi)
agent_wrapper.setup(Prompts.SYSTEM_PROMPT)

result = asyncio.run(agent_wrapper.run(Prompts.USER_PROMPT))

agent_wrapper.print_results(result)


##########################################
# Day 5: Logging and evaluation

agent_log = AgentLog()
agent_log.log_interaction_to_file(agent_wrapper.agent, result['conversation'])