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
        You are a helpful assistant for searching through technical documentation.
        Use the search tool to find relevant information from the course materials before answering questions.  

        If you can find specific information through search, use it to provide accurate answers.

        Always include references by citing the filename of the source material you used.  
        When citing the reference, use the full path to the GitHub repository: "https://github.com/mvrey/RAGBot/blob/main/"
        Format: [LINK TITLE](FULL_GITHUB_LINK)

        If the search doesn't return relevant results, let the user know and provide general guidance.
        """

    USER_PROMPT = "What is particularly important to remember during this setup?"

    EVALUATION_PROMPT = """
        Use this checklist to evaluate the quality of an AI agent's answer (<ANSWER>) to a user question (<QUESTION>).
        We also include the entire log (<LOG>) for analysis.

        For each item, check if the condition is met. 

        Checklist:

        - instructions_follow: The agent followed the user's instructions (in <INSTRUCTIONS>)
        - instructions_avoid: The agent avoided doing things it was told not to do  
        - answer_relevant: The response directly addresses the user's question  
        - answer_clear: The answer is clear and correct  
        - answer_citations: The response includes proper citations or sources when required  
        - completeness: The response is complete and covers all key aspects of the request
        - tool_call_search: Is the search tool invoked? 

        Output true/false for each check and provide a short explanation for your judgment.
        """
    
    USER_EVALUATION_PROMPT_FORMAT = """
        <INSTRUCTIONS>{instructions}</INSTRUCTIONS>
        <QUESTION>{question}</QUESTION>
        <ANSWER>{answer}</ANSWER>
        <LOG>{log}</LOG>
        """


    