import json
import secrets
from pathlib import Path
from datetime import datetime
from pydantic_ai.messages import ModelMessagesTypeAdapter
from src.Prompts import Prompts
from src.EvaluationCheck import EvaluationChecklist

LOG_DIR = Path('logs')
LOG_DIR.mkdir(exist_ok=True)


class AgentLog:
    def __init__(self):
        self.log_entries = []
        self.current_step = 0


    def log_entry(self, agent, messages, source="user"):
        tools = []

        for ts in agent.toolsets:
            tools.extend(ts.tools.keys())

        dict_messages = ModelMessagesTypeAdapter.dump_python(messages)

        return {
            "agent_name": agent.name,
            "system_prompt": agent._instructions,
            "provider": agent.model.system,
            "model": agent.model.model_name,
            "tools": tools,
            "messages": dict_messages,
            "source": source
        }


    def serializer(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")


    def log_interaction_to_file(self, agent, messages, source='user'):
        entry = self.log_entry(agent, messages, source)

        ts = entry['messages'][-1]['timestamp']
        ts_str = ts.strftime("%Y%m%d_%H%M%S")
        rand_hex = secrets.token_hex(3)

        filename = f"{agent.name}_{ts_str}_{rand_hex}.json"
        filepath = LOG_DIR / filename

        with filepath.open("w", encoding="utf-8") as f_out:
            json.dump(entry, f_out, indent=2, default=self.serializer)

        return filepath
    

    def load_log_file(self, log_file):
        with open(log_file, 'r') as f_in:
            log_data = json.load(f_in)
            log_data['log_file'] = log_file
            return log_data
        

    def simplify_log_messages(self, messages):
        log_simplified = []

        for m in messages:
            parts = []
        
            for original_part in m['parts']:
                part = original_part.copy()
                kind = part['part_kind']
        
                match kind:
                    case 'user-prompt':
                        del part['timestamp']
                    case 'tool-call':
                        del part['tool_call_id']
                    case 'tool-return':
                        del part['tool_call_id']
                        del part['metadata']
                        del part['timestamp']
                        # Replace actual search results with placeholder to save tokens
                        part['content'] = 'RETURN_RESULTS_REDACTED'
                    case 'text':
                        del part['id']
        
                parts.append(part)
        
            message = {
                'kind': m['kind'],
                'parts': parts
            }
        
            log_simplified.append(message)
        return log_simplified
    

    async def evaluate_log_record(self, eval_agent, log_record):
        messages = log_record['messages']

        instructions = log_record['system_prompt']
        question = messages[0]['parts'][0]['content']
        answer = messages[-1]['parts'][0]['content']

        log_simplified = self.simplify_log_messages(messages)
        log = json.dumps(log_simplified)

        user_prompt = Prompts.USER_EVALUATION_PROMPT_FORMAT.format(
            instructions=instructions,
            question=question,
            answer=answer,
            log=log
        )

        result = await eval_agent.run(user_prompt, output_type=EvaluationChecklist)
        return result.output 
