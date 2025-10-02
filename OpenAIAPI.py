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


    def llm(self, prompt):
        messages = [
            {"role": "user", "content": prompt}
        ]

        openai_client = OpenAI(api_key=self.get_openai_api_key())
        response = openai_client.chat.completions.create(
            model=self.gpt_model,
            messages=messages
        )

        return response.choices[0].message.content