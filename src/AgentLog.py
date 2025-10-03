import json
import secrets
from pathlib import Path
from datetime import datetime
from pydantic_ai.messages import ModelMessagesTypeAdapter

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
