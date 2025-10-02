import io
import os
import re
from tqdm import tqdm
from openai import OpenAI
from minsearch import Index
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm
import numpy as np
from minsearch import VectorSearch
import json

import TechnicalDocumentation
import TextChunker
import Prompts
import OpenAIAPI


gpt_model = 'gpt-4.1-nano'

##########################################
# Day 2: Chunking







#Chunking using LLM (e.g., GPT-4)







openai_api = OpenAIAPI()
openai_client = OpenAI(api_key=openai_api.get_openai_api_key())


# CONTINUE EDITING HERE

def intelligent_chunking(text):
    prompt = Prompts.CHUNKING_PROMPT.strip().format(document=text)
    response = llm(prompt)
    sections = response.split('---')
    sections = [s.strip() for s in sections if s.strip()]
    return sections


##########################################
# Day 3: Indexing and searching

def text_search(query, dtc_fastapi):
    index = Index(
    text_fields=["chunk", "title", "description", "filename"],
    keyword_fields=[]
    )

    index.fit(dtc_fastapi)

    return index.search(query, num_results=2)


def vector_search(query, dtc_fastapi):
    embedding_model = SentenceTransformer('multi-qa-distilbert-cos-v1')
    faq_embeddings = []
    print(f"Encoding text:\n")

    for d in tqdm(dtc_fastapi):
        if 'content' not in d:
            text = ''
        else:
            #TODO: replace the question with a set of possible questions that ought to be asked about about the docs. Let the llm suggest some possible questions.
            text = '''question +''' ' ' + d['content']
        v = embedding_model.encode(text)
        faq_embeddings.append(v)

    faq_embeddings = np.array(faq_embeddings)

    faq_vindex = VectorSearch()
    faq_vindex.fit(faq_embeddings, dtc_fastapi)

    q = embedding_model.encode(query)
    return faq_vindex.search(q, num_results=2)


def hybrid_search(query, dtc_fastapi):
    text_results = text_search(query, dtc_fastapi)
    vector_results = vector_search(query, dtc_fastapi)
    
    # Combine and deduplicate results
    seen_ids = set()
    combined_results = []

    for result in text_results + vector_results:
        print(result)
        if result['chunk'] not in seen_ids:
            seen_ids.add(result['chunk'])
            combined_results.append(result)
    
    return combined_results


##########################################
# Day 4: Agents and tools





##########################################

#Read repo docs
docs = TechnicalDocumentation('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main')
dtc_fastapi = docs.get_repo_doc_files()

print(f"Repository documents: {len(dtc_fastapi)}")




##########################################

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
'''
question = 'Powershell'

#Index method 1 : Lexical search index


#Index method 2: Semantic search index using sentence-transformers (vectors)


#Index method 3: Hybrid search index using both lexical and semantic search
results = hybrid_search(question, dtc_fastapi)
print("Hybrid search results:\n")
print(results)
'''

##########################################



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