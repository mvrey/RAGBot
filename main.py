import asyncio
import json
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

chunking_strategy = ChunkingStrategy(ChunkingStrategy.PARAGRAPH)
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

### Log llm call

agent_log = AgentLog()
agent_log.log_interaction_to_file(agent_wrapper.agent, result['conversation'])

### Evaluate llm response

from src.EvaluationCheck import EvaluationChecklist
from pydantic_ai import Agent

log_record = agent_log.load_latest_log_file()

user_prompt = Prompts.USER_EVALUATION_PROMPT_FORMAT.format(
    instructions = log_record['system_prompt'],
    question = log_record['messages'][0]['parts'][0]['content'],
    answer = log_record['messages'][-1]['parts'][0]['content'],
    log = json.dumps(log_record['messages'])
)

eval_agent = Agent(
    name='eval_agent',
    model='gpt-4.1-nano',
    instructions=Prompts.EVALUATION_PROMPT,
    output_type=EvaluationChecklist
)

result = asyncio.run(agent_log.evaluate_log_record(eval_agent, log_record))

print(result.summary)

for check in result.checklist:
    print(check)


############################### Generate test questions

from pydantic import BaseModel

class QuestionsList(BaseModel):
    questions: list[str]

question_generator = Agent(
    name="question_generator",
    instructions=Prompts.QUESTION_GENERATION_PROMPT,
    model='gpt-4.1-nano',
    output_type=QuestionsList
)

# sample (1) records from our dataset to generate questions from
import random

sample = random.sample(dtc_fastapi, 1)
prompt_docs = [d['chunk'] for d in sample if 'chunk' in d]
prompt = json.dumps(prompt_docs)

result = asyncio.run(question_generator.run(prompt))
questions = result.output.questions

# Iterate over each of the question, ask our agent and log the results

from tqdm.auto import tqdm

print("\nGenerated questions:\n")
for q in tqdm(questions):
    print(q)

    result = asyncio.run(agent_wrapper.run(prompt=q))
    print(result['conversation'])

    agent_log.log_interaction_to_file(
        agent_wrapper.agent,
        result['conversation'],
        source='ai-generated'
    )

    print()

# Run evaluation on them with our evaluation agent.
# First, collect all the AI-generated logs for the v2 agent:

from src.AgentLog import LOG_DIR

eval_set = []

for log_file in LOG_DIR.glob('*.json'):
    if 'faq_agent' not in log_file.name:
        continue

    log_record = agent_log.load_log_file(log_file)
    if log_record['source'] != 'ai-generated':
        continue

    eval_set.append(log_record)

# And evaluate them

eval_results = []

for log_record in tqdm(eval_set):
    eval_result = asyncio.run(agent_log.evaluate_log_record(eval_agent, log_record))
    eval_results.append((log_record, eval_result))

# Transform data into a Pandas DataFrame

rows = []

for log_record, eval_result in eval_results:
    messages = log_record['messages']

    row = {
        'file': log_record['log_file'].name,
        'question': messages[0]['parts'][0]['content'],
        'answer': messages[-1]['parts'][0]['content'],
    }

    checks = {c.check_name: c.check_pass for c in eval_result.checklist}
    row.update(checks)

    rows.append(row)


#Display the results and also calculate some statistics (Only works in Jupyter, not in a .py file)

import pandas as pd

df_evals = pd.DataFrame(rows)
df_evals.mean(numeric_only=True)