from typing import List, Any, Dict
from pydantic_ai import Agent
from SearchStrategy import SearchStrategy, SearchStrategyType


class AgentWrapper:

    def __init__(self, documents: List[Dict], agent_name: str = "faq_agent", model: str = "gpt-4.1-nano"):
        self.documents = documents
        self.agent_name = agent_name
        self.model = model
        self.search_strategy = SearchStrategy()
        self.agent = None
        
        def text_search(query: str) -> str:
            """Search the documentation and return formatted results."""
            results = self.search_strategy.execute_strategy(SearchStrategyType.HYBRID, query, self.documents)
            
            # Format the results in a readable way
            formatted_results = []
            for idx, result in enumerate(results, 1):
                chunk = result.get('chunk', '')
                filename = result.get('filename', 'unknown file')
                formatted_results.append(f"Result {idx} from {filename}:\n{chunk}\n")
            
            return "\n".join(formatted_results) if formatted_results else "No relevant information found."
        
        # Add schema to the function
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
        
        self.text_search = text_search


    def setup(self, instructions: str) -> None:
        self.agent = Agent(
            name=self.agent_name,
            instructions=instructions,
            tools=[self.text_search],
            model=self.model
        )


    async def run(self, prompt: str) -> Dict:
        if not self.agent:
            raise ValueError("Agent not initialized. Call setup() first.")
        
        result = await self.agent.run(user_prompt=prompt)
        return {
            'conversation': result.all_messages(),
            'response': result.output
        }


    def print_results(self, result: Dict) -> None:
        print("Conversation History:")
        for message in result['conversation']:
            print(f"\n{message}")

        print("\nFinal Response:")
        print(result['response'])
