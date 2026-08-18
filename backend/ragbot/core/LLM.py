"""Chat model selection.

pydantic-ai takes provider-prefixed model strings ("google-gla:gemini-2.5-flash",
"openai:gpt-4.1-nano"), so switching provider is a one-line .env change rather than
a code change. This module owns the default and the key check.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = 'google-gla:gemini-2.5-flash'

# Which credential each provider prefix needs, so a missing key is reported by name
# up front instead of surfacing as a failure on the first question.
API_KEY_BY_PREFIX = {
    'google-gla': 'GOOGLE_API_KEY',
    'google-vertex': 'GOOGLE_API_KEY',
    'openai': 'OPENAI_API_KEY',
    'anthropic': 'ANTHROPIC_API_KEY',
    'groq': 'GROQ_API_KEY',
    'mistral': 'MISTRAL_API_KEY',
}


def get_model_name() -> str:
    """The chat model to use, from LLM_MODEL in .env."""
    return os.getenv('LLM_MODEL', '').strip() or DEFAULT_MODEL


def required_api_key(model_name: str = None) -> str:
    """Name of the environment variable this model needs, if we can tell."""
    model_name = model_name or get_model_name()
    prefix = model_name.split(':', 1)[0] if ':' in model_name else 'openai'
    return API_KEY_BY_PREFIX.get(prefix, '')


def missing_api_key(model_name: str = None) -> str:
    """Return the missing credential's name, or '' when it is set."""
    key = required_api_key(model_name)
    if key and not os.getenv(key):
        return key
    return ''
