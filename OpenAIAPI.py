from openai import OpenAI
import os
from dotenv import load_dotenv
from typing import Optional

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


    def send_prompt(self, messages, tool_list):
        openai_client = OpenAI(api_key=self.get_openai_api_key())
        response = openai_client.chat.completions.create(
            model=self.gpt_model,
            messages=messages
            #TODO : Check if this works with no tools
            tools=tool_list
        )

        return response.choices[0].message.content