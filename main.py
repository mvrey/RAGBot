from src.TechnicalDocumentation import TechnicalDocumentation
from src.ChunkingStrategy import ChunkingStrategy
from src.SearchStrategy import SearchStrategy
from src.Prompts import SYSTEM_PROMPT, USER_PROMPT


##########################################
# Day 1: Read repo files

#Read repo docs
docs = TechnicalDocumentation('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main')
dtc_fastapi = docs.get_repo_doc_files()

print(f"Repository documents: {len(dtc_fastapi)}")


##########################################
# Day 2: Chunking

chunking_strategy = ChunkingStrategy()
chunking_strategy.chunk(ChunkingStrategy.MARKDOWN, docs)

docs.print_summary()


##########################################
# Day 3: Indexing and searching

search_strategy = SearchStrategy()
results = search_strategy.execute_strategy(SearchStrategy.HYBRID, Prompts.USER_PROMPT, dtc_fastapi)

print("Search results:\n")
print(results)


##########################################
# Day 4: Agents and tools

from typing import List, Any
from pydantic_ai import Agent
import asyncio

def text_search(dtc_fastapi, query: str) -> List[Any]:
    return dtc_fastapi.search(query, num_results=5)

agent = Agent(
    name="faq_agent",
    instructions=Prompts.SYSTEM_PROMPT,
    tools=[text_search],
    model='gpt-4o-mini'
)

result = asyncio.run(agent.run(user_prompt=Prompts.USER_PROMPT))

result.new_messages()
print(result.final_response)