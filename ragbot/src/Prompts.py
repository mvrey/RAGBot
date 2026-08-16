class Prompts:
    # System prompts
    CHUNKING_PROMPT = """
        Split the provided document into logical sections that make sense for technical documentation. Each section should be self-contained and cover a specific topic or concept.

        <DOCUMENT>
        {document}
        </DOCUMENT>

        Use this format:

        ## Section Name

        Section content with all relevant details

        ---

        ## Another Section Name

        Another section content

        ---
        """

    SYSTEM_PROMPT = """
        You are a code documentation assistant. You answer questions about a single
        software repository: how it works, where functionality lives, what the APIs and
        dependencies are.

        How to work:
        - Always start with search_code. Search using the wording of the question, and
          again with likely identifier names if the first search is thin.
        - Use read_file to confirm what the code actually does before you explain it.
          Retrieved snippets can be partial - never describe behaviour you have not read.
        - Use list_files to orient yourself when a question is about structure, or when
          search does not surface the right file.
        - Follow references across files. If a function calls something defined
          elsewhere, read that too before explaining the behaviour.

        How to answer:
        - Cite every claim with a path and line range, for example
          `src/TextSearcher.py:59-72`.
        - Quote the relevant lines when a short excerpt makes the answer concrete.
        - Explain what the code does, not what you assume it should do.

        Guardrails:
        - Never invent files, functions, parameters, or APIs. If it is not in the
          repository, say so plainly.
        - If the search returns nothing useful, say what you looked for and suggest
          where the user might point you instead. Do not fall back on general knowledge
          about how such a project is "usually" built.
        - When the code is ambiguous or you are inferring intent, label it as inference.
        - Stay within this repository. Decline questions unrelated to it.
        """

    CITATION_SUFFIX_FORMAT = """

        When citing, also link to the source on GitHub using this base URL:
        {blob_url_base}
        Format: [path/to/file.py:12-34]({blob_url_base}path/to/file.py#L12-L34)
        """

    USER_PROMPT = "How does the hybrid search combine keyword and vector results?"

    EVALUATION_PROMPT = """
        Use this checklist to evaluate the quality of an AI agent's answer (<ANSWER>) to a user question (<QUESTION>).
        We also include the entire log (<LOG>) for analysis.

        For each item, check if the condition is met.

        Checklist:

        - instructions_follow: The agent followed the user's instructions (in <INSTRUCTIONS>)
        - instructions_avoid: The agent avoided doing things it was told not to do
        - answer_relevant: The response directly addresses the user's question
        - answer_clear: The answer is clear and correct
        - answer_citations: The response cites specific files and line ranges from the repository
        - completeness: The response is complete and covers all key aspects of the request
        - tool_call_search: Is the search tool invoked?
        - grounded_in_code: Every claim about the code is supported by retrieved or read source, with nothing invented

        Output true/false for each check and provide a short explanation for your judgment.
        """

    USER_EVALUATION_PROMPT_FORMAT = """
        <INSTRUCTIONS>{instructions}</INSTRUCTIONS>
        <QUESTION>{question}</QUESTION>
        <ANSWER>{answer}</ANSWER>
        <LOG>{log}</LOG>
        """

    QUESTION_GENERATION_PROMPT = """
        You are helping to create test questions for a code repository.

        Based on the provided source code, generate realistic questions that a developer
        new to this codebase might ask.

        The questions should:

        - Be natural and varied in style
        - Range from simple to complex
        - Cover how things work, where functionality is implemented, APIs, and dependencies

        Generate one question for each record.
        """

    @classmethod
    def system_prompt_for(cls, blob_url_base: str = None) -> str:
        """System prompt, extended with GitHub linking when the repo URL is known."""
        if not blob_url_base:
            return cls.SYSTEM_PROMPT
        return cls.SYSTEM_PROMPT + cls.CITATION_SUFFIX_FORMAT.format(
            blob_url_base=blob_url_base
        )
