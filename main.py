import json
import TechnicalDocumentation
import ChunkingStrategy
import TextSearcher
import SearchStrategy
import Prompts
import OpenAIAPI


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

chat_messages = [
    {"role": "system", "content": Prompts.SYSTEM_PROMPT},
    {"role": "user", "content": Prompts.USER_PROMPT}
]

openai_api = OpenAIAPI()
response =  openai_api.send_prompt(chat_messages, [text_search_tool])

assistant_message = response.choices[0].message


# EDIT FROM HERE

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