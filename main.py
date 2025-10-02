import io
import os
import re
from openai import OpenAI
from minsearch import Index
from tqdm.auto import tqdm
import numpy as np
import json

import TechnicalDocumentation
import TextChunker
import TextSearcher


##########################################
# Day 1: Read repo files

#Read repo docs
docs = TechnicalDocumentation('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main')
dtc_fastapi = docs.get_repo_doc_files()

print(f"Repository documents: {len(dtc_fastapi)}")


##########################################
# Day 2: Chunking

text_chunker = TextChunker("")

# Method 1: Sliding window simple chunking by characters
docs.chunk_by_characters()

# OR

# Method 2: Chunking by paragraphs
docs.chunk_by_paragraphs()

# OR

# Method 3: Chunking by markdown headings
docs.chunk_by_markdown_headings()

# OR

# Method 4: Intelligent chunking using LLM (e.g., GPT-4)
docs.llm_chunking()


docs.print_summary()


##########################################
# Day 3: Indexing and searching


question = 'Powershell'
text_searcher = TextSearcher()

#Index method 1 : Lexical search index
results = text_searcher.text_search(question, dtc_fastapi)

# OR

#Index method 2: Semantic search index using sentence-transformers (vectors)
results = text_searcher.vector_search(question, dtc_fastapi)

# OR

#Index method 3: Hybrid search index using both lexical and semantic search
results = text_searcher.hybrid_search(question, dtc_fastapi)

print("Search results:\n")
print(results)


##########################################
# Day 4: Agents and tools


text_search_tool = {
    "type": "function",
    "function": {
        "name": "text_search",
        "description": "Search the FAQ database",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query text to look up in the course FAQ."
                }
            },
            "required": ["query"]
        }
    }
}

system_prompt = """
You are a helpful assistant for a course. 
"""

question = "What is particularly important to remember during this setup?"

chat_messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": question}
]

response = openai_client.chat.completions.create(
    model=gpt_model,
    messages=chat_messages,
    tools=[text_search_tool]
)

assistant_message = response.choices[0].message

if assistant_message.tool_calls:
    # Handle tool calls
    tool_call = assistant_message.tool_calls[0]
    
    if tool_call.function.name == "text_search":
        # Parse the function arguments
        function_args = json.loads(tool_call.function.arguments)
        result = text_search(function_args["query"], dtc_fastapi)
        
        # Add assistant's message and tool results to the conversation
        chat_messages.append({"role": "assistant", "content": None, "tool_calls": [tool_call]})
        chat_messages.append({"role": "tool", "content": json.dumps(result), "tool_call_id": tool_call.id})
        
        # Get the final response
        final_response = openai_client.chat.completions.create(
            model=gpt_model,
            messages=chat_messages
        )
        print(final_response.choices[0].message.content)
else:
    # If no tool was called, just print the response
    print(assistant_message.content)