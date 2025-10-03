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
    
    SYSTEM_PROMPT = "You are a helpful assistant for searching through technical documentation."

    USER_PROMPT = "What is particularly important to remember during this setup?"