import io
import os
import zipfile
import requests
import frontmatter
import re
from tqdm import tqdm
from openai import OpenAI
from minsearch import Index
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm
import numpy as np
from minsearch import VectorSearch
import json




##########################################
# Day 1: Read repo files

def read_repo_data(repo_owner, repo_name):
    prefix = 'https://codeload.github.com' 
    url = f'{prefix}/{repo_owner}/{repo_name}/zip/refs/heads/main'
    resp = requests.get(url)
    
    if resp.status_code != 200:
        raise Exception(f"Failed to download repository: {resp.status_code}")

    repository_data = []
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    
    for file_info in zf.infolist():
        filename = file_info.filename
        filename_lower = filename.lower()

        if not (filename_lower.endswith('.md') 
            or filename_lower.endswith('.mdx')):
            continue
    
        try:
            with zf.open(file_info) as f_in:
                content = f_in.read().decode('utf-8', errors='ignore')
                post = frontmatter.loads(content)
                data = post.to_dict()
                data['filename'] = filename
                repository_data.append(data)
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            continue
    
    zf.close()
    return repository_data


##########################################
# Day 2: Chunking

# Simple sliding window chunking by characters
def sliding_window(seq, size, step):
    if size <= 0 or step <= 0:
        raise ValueError("size and step must be positive")

    n = len(seq)
    result = []
    for i in range(0, n, step):
        chunk = seq[i:i+size]
        result.append({'start': i, 'chunk': chunk})
        if i + size >= n:
            break

    return result


#Chunking by paraghps
def chunk_by_paragraphs(text):
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return [{'chunk': p} for p in paragraphs]


#chunking by levels of headings
def split_markdown_by_level(text, level=2):
    # This regex matches markdown headers
    # For level 2, it matches lines starting with "## "
    header_pattern = r'^(#{' + str(level) + r'} )(.+)$'
    pattern = re.compile(header_pattern, re.MULTILINE)

    # Split and keep the headers
    parts = pattern.split(text)
    
    sections = []
    for i in range(1, len(parts), 3):
        # We step by 3 because regex.split() with
        # capturing groups returns:
        # [before_match, group1, group2, after_match, ...]
        # here group1 is "## ", group2 is the header text
        header = parts[i] + parts[i+1]  # "## " + "Title"
        header = header.strip()

        # Get the content after this header
        content = ""
        if i+2 < len(parts):
            content = parts[i+2].strip()

        section = {'chunk': f'{header}\n\n{content}' if content else header}
        sections.append(section)
    
    return sections


#Chunking using LLM (e.g., GPT-4)
prompt_template = """
Split the provided document into logical sections
that make sense for a Q&A system.

Each section should be self-contained and cover
a specific topic or concept.

<DOCUMENT>
{document}
</DOCUMENT>

Use this format:

## Section Name

Section content with all relevant details

---

## Another Section Name

Another section content

---
""".strip()


import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_openai_api_key():
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set. Please check your .env file.")
    return api_key

openai_client = OpenAI(api_key=get_openai_api_key())


def llm(prompt, model='gpt-3.5-turbo'):
    messages = [
        {"role": "user", "content": prompt}
    ]

    response = openai_client.responses.create(
        model='gpt-3.5-turbo',
        input=messages
    )

    return response.output_text


def intelligent_chunking(text):
    prompt = prompt_template.format(document=text)
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
dtc_fastapi = read_repo_data('mvrey', 'RAGBot')

print(f"FastAPI documents: {len(dtc_fastapi)}")

processed_docs = 0
skipped_docs = 0


##########################################


# Method 1: Sliding window simple chunking by characters
'''
for doc in dtc_fastapi:
    doc_copy = doc.copy()
    if 'content' not in doc_copy:
        skipped_docs += 1
        continue
    
    processed_docs += 1
    doc_content = doc_copy.pop('content')
    chunks = sliding_window(doc_content, 2000, 1000)
    for chunk in chunks:
        chunk.update(doc_copy)
    dtc_fastapi.extend(chunks)
'''

# Method 2: Chunking by paragraphs

for doc in dtc_fastapi:
    doc_copy = doc.copy()
    if 'content' not in doc_copy:
        skipped_docs += 1
        continue
    
    processed_docs += 1
    doc_content = doc_copy.pop('content')
    chunks = chunk_by_paragraphs(doc_content)
    dtc_fastapi.extend(chunks)

'''
# Method 3: Chunking by markdown headings
for doc in dtc_fastapi:
    doc_copy = doc.copy()
    if 'content' not in doc_copy:
        skipped_docs += 1
        continue
    
    processed_docs += 1
    doc_content = doc_copy.pop('content')
    chunks = split_markdown_by_level(doc_content, level=2)
    dtc_fastapi.extend(chunks)
'''
'''
# Method 4: Intelligent chunking using LLM (e.g., GPT-4)
for doc in tqdm(dtc_fastapi):
    doc_copy = doc.copy()
    doc_content = doc_copy.pop('content')

    sections = intelligent_chunking(doc_content)
    for section in sections:
        section_doc = doc_copy.copy()
        section_doc['section'] = section
        dtc_fastapi.append(section_doc)
'''


print(f"Processed documents: {processed_docs}, Skipped documents: {skipped_docs}")
print(f"FastAPI chunks: {len(dtc_fastapi)}")

#print(f"Sample chunk:\n{dtc_fastapi[100]}")


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
        "required": ["query"],
        "additionalProperties": False
    }
}

system_prompt = """
You are a helpful assistant for a course. 
"""

question = "Gimme the Powershell command"

chat_messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": question}
]

response = openai_client.responses.create(
    model='gpt-4o-mini',
    input=chat_messages,
    tools=[text_search_tool]
)

##

call = response.output[0]

#[ResponseOutputMessage(id='msg_063a84694f8714410068de58a572c481918058783caa7b82ea', content=[ResponseOutputText(annotations=[], text='Could you please specify what task or function you would like to accomplish with the PowerShell command? This will help me provide the specific command you need.', type='output_text', logprobs=[])], role='assistant', status='completed', type='message')]

#arguments = json.loads(call.arguments)
#result = text_search(**arguments)
result = text_search(call.content[0].text, dtc_fastapi)

call_output = {
    "type": "function_call_output",
    "call_id": call.id,
    "output": json.dumps(result),
}

##

chat_messages.append(call)
chat_messages.append(call_output)

response = openai_client.responses.create(
    model='gpt-4o-mini',
    input=chat_messages,
    tools=[text_search_tool]
)

print(response.output_text)