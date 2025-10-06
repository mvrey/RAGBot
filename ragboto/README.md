# RAGBot
An llm-powered RAG system to interactively search and answer about documentation in any github repository

## Setup

1. Make sure you have Python installed on your system
2. Install the required dependencies (listed in pyproject.toml)
3. Set up your OpenAI API key:

### Setting up the OpenAI API Key

The application requires an OpenAI API key to function. To set it up:

1. Get your API key from [OpenAI's website](https://platform.openai.com/api-keys)
2. Set it as an environment variable:

On Windows (PowerShell):
```powershell
$env:OPENAI_API_KEY = 'your-api-key-here'
```

On Linux/macOS:
```bash
export OPENAI_API_KEY='your-api-key-here'
```

Alternatively, you can create a `.env` file in the project root with:
```
OPENAI_API_KEY=your-api-key-here
```

**Important**: Never commit your API key to version control. Make sure to add `.env` to your `.gitignore` file.
