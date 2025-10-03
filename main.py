from src.TechnicalDocumentation import TechnicalDocumentation
from src.ChunkingStrategy import ChunkingStrategy
from src.SearchStrategy import SearchStrategy, SearchStrategyType
from src.Prompts import Prompts


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

from typing import List, Any
from pydantic_ai import Agent
import asyncio

def text_search(query: str) -> List[Any]:
    return search_strategy.execute_strategy(SearchStrategyType.TEXT, query, dtc_fastapi)

# Add schema information to the function
text_search.schema = {
    "name": "text_search",
    "description": "Search through the documentation for relevant information",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up in the documentation"
            }
        },
        "required": ["query"]
    }
}

agent = Agent(
    name="faq_agent",
    instructions=Prompts.SYSTEM_PROMPT,
    tools=[text_search],  # Pass the actual function with its schema
    model='gpt-4.1-nano'
)

result = asyncio.run(agent.run(user_prompt=Prompts.USER_PROMPT))

# Print all messages in the conversation
print("Conversation History:")
all_messages = result.all_messages()  # Call the method
for message in all_messages:
    print(f"\n{message}")

# Print the final response
print("\nFinal Response:")
print(result.output)