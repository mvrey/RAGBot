import streamlit as st
import asyncio
import logs

from src.TechnicalDocumentation import TechnicalDocumentation
from src.ChunkingStrategy import ChunkingStrategy
from src.SearchStrategy import SearchStrategy, SearchStrategyType


# --- Streamlit Page Config ---
st.set_page_config(page_title="AI Documentation Assistant", page_icon="🤖", layout="centered")
st.title("🤖 AI Documentation Assistant")
st.caption("Step-by-step assistant for exploring GitHub repositories")


# --- User Inputs ---
repo_url = st.text_input(
    "🔗 Enter GitHub repository URL:",
    "https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main"
)

chunking_method_name = st.selectbox(
    "🧩 Select Chunking Method:",
    options=[c.name for c in ChunkingStrategy],
    index=1  # Default: PARAGRAPH
)

search_method_name = st.selectbox(
    "🔍 Select Search Method:",
    options=[s.name for s in SearchStrategyType],
    index=1  # Default: VECTOR
)


# --- Initialize default session state ---
default_states = {
    "repo_downloaded": False,
    "repo_chunked": False,
    "repo_indexed": False,
    "docs": None,
    "chunked_docs": None,
    "search_strategy": None,
    "search_method": None,
    "messages": [],
}
for key, val in default_states.items():
    if key not in st.session_state:
        st.session_state[key] = val


# --- Step 1: Download Repo ---
def download_repo():
    st.write(f"📦 Downloading repository from: {repo_url}")
    docs = TechnicalDocumentation(repo_url)
    docs.get_repo_doc_files()  # load internal data
    st.session_state.docs = docs
    st.session_state.chunked_docs = None
    st.session_state.search_strategy = None
    st.session_state.repo_downloaded = True
    st.session_state.repo_chunked = False
    st.session_state.repo_indexed = False
    st.success("✅ Repository downloaded successfully!")


# --- Step 2: Chunk Repo ---
def chunk_repo():
    st.write("🔄 Chunking repository documents...")
    chunking_method = ChunkingStrategy[chunking_method_name]
    docs = st.session_state.docs
    chunked_docs = chunking_method.chunk(docs)
    st.session_state.chunked_docs = chunked_docs
    st.session_state.search_strategy = None
    st.session_state.repo_chunked = True
    st.session_state.repo_indexed = False
    st.success(f"✅ Chunking complete using {chunking_method.name} strategy.")


# --- Step 3: Index Repo ---
def index_repo():
    st.write("📇 Indexing documents...")
    st.session_state.search_method = SearchStrategyType[search_method_name]
    st.session_state.search_strategy = SearchStrategy()
    st.session_state.repo_indexed = True
    st.success(f"✅ Indexing complete using {st.session_state.search_method.name} search method.")


# --- Buttons Section ---
st.subheader("⚙️ Workflow Controls")
col1, col2, col3 = st.columns(3)

with col1:
    st.button(
        "⬇️ Download Repo",
        on_click=download_repo,
        disabled=False
    )

with col2:
    st.button(
        "✂️ Chunk Documents",
        on_click=chunk_repo,
        disabled=not st.session_state.repo_downloaded
    )

with col3:
    st.button(
        "📈 Index Contents",
        on_click=index_repo,
        disabled=not st.session_state.repo_chunked
    )

# --- Status Bar ---
status = []
if st.session_state.repo_downloaded:
    status.append("📦 Repo downloaded")
if st.session_state.repo_chunked:
    status.append("✂️ Docs chunked")
if st.session_state.repo_indexed:
    status.append("📈 Indexed")

if status:
    st.success(" → ".join(status))
else:
    st.info("⬇️ Start by downloading a repository.")


st.divider()

# --- Chat Section ---
if st.session_state.repo_indexed and st.session_state.search_strategy:
    st.subheader("💬 Chat with your documentation")

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask your question..."):
        # User message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Assistant response
        with st.chat_message("assistant"):
            with st.spinner("Searching..."):
                result = st.session_state.search_strategy.execute_strategy(
                    st.session_state.search_method,
                    prompt,
                    st.session_state.chunked_docs
                )
                st.markdown(result)

        # Save response
        st.session_state.messages.append({"role": "assistant", "content": str(result)})

        # Log interaction
        logs.log_interaction_to_file(st.session_state.search_strategy, result)
else:
    st.info("⚙️ Complete all steps (Download → Chunk → Index) before chatting.")
