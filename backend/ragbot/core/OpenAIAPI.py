from openai import OpenAI
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class OpenAIAPI:
    
    def __init__(self):
        self.gpt_model = 'gpt-4.1-nano'


    def get_openai_api_key(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set. Please check your .env file.")
        return api_key


    def send_prompt(self, messages, tool_list=None):
        openai_client = OpenAI(api_key=self.get_openai_api_key())
        # The API rejects an explicit tools=None, so only pass it when there are tools.
        optional_args = {'tools': tool_list} if tool_list else {}
        response = openai_client.chat.completions.create(
            model=self.gpt_model,
            messages=messages,
            **optional_args
        )

        return response.choices[0].message.content