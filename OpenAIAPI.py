import openai
import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables from .env file
load_dotenv()

class OpenAIAPI:
    def __init__(self):
        pass


    def get_openai_api_key(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set. Please check your .env file.")
        return api_key

    openai_client = OpenAI(api_key=get_openai_api_key())


    def llm(self, prompt, model=gpt_model):
        messages = [
            {"role": "user", "content": prompt}
        ]

        response = openai_client.chat.completions.create(
            model=model,
            messages=messages
        )

        return response.choices[0].message.content