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

### Log llm call

agent_log = AgentLog()
agent_log.log_interaction_to_file(agent_wrapper.agent, result['conversation'])

### Evaluate llm response

from src.EvaluationCheck import EvaluationChecklist
from pydantic_ai import Agent

log_record = agent_log.load_log_file('./logs/faq_agent_20251003_112139_6e2e73.json')

user_prompt = Prompts.USER_EVALUATION_PROMPT_FORMAT.format(
    instructions = log_record['system_prompt'],
    question = log_record['messages'][0]['parts'][0]['content'],
    answer = log_record['messages'][-1]['parts'][0]['content'],
    log = json.dumps(log_record['messages'])
)

eval_agent = Agent(
    name='eval_agent',
    model='gpt-4.1-mini',
    instructions=Prompts.EVALUATION_PROMPT,
    output_type=EvaluationChecklist
)

result = asyncio.run(agent_log.evaluate_log_record(eval_agent, log_record))

print(result.summary)

for check in result.checklist:
    print(check)