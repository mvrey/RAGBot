import streamlit as st
import asyncio

from src.TechnicalDocumentation import TechnicalDocumentation
from src.ChunkingStrategy import ChunkingStrategy
from src.SearchStrategy import SearchStrategy, SearchStrategyType
from src.AgentWrapper import AgentWrapper
from src.AgentLog import AgentLog

# --- Page config ---
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
    index=1
)

search_method_name = st.selectbox(
    "🔍 Select Search Method:",
    options=[s.name for s in SearchStrategyType],
    index=1
)

system_prompt = st.text_area(
    "📝 System Prompt (for agent):",
    value="You are an AI assistant. Answer questions based on the repository."
)


# --- Initialize session state ---
defaults = {
    "docs": None,
    "dtc_fastapi": None,
    "repo_downloaded": False,
    "repo_chunked": False,
    "repo_indexed": False,
    "agent_wrapper": None,
    "search_strategy": None,
    "search_method": None,
    "messages": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# --- Step 1: Download Repo ---
def download_repo():
    st.write(f"📦 Downloading repository from: {repo_url}")
    docs = TechnicalDocumentation(repo_url)
    dtc_fastapi = docs.get_repo_doc_files()
    st.session_state.docs = docs
    st.session_state.dtc_fastapi = dtc_fastapi
    st.session_state.repo_downloaded = True
    st.session_state.repo_chunked = False
    st.session_state.repo_indexed = False
    st.session_state.agent_wrapper = None
    st.success(f"✅ Repository downloaded ({len(dtc_fastapi)} files/chunks)")


# --- Step 2: Chunk Documents ---
def chunk_repo():
    if not st.session_state.docs:
        st.warning("Download the repo first.")
        return
    st.write("🔄 Chunking repository documents...")
    chunking_method = ChunkingStrategy[chunking_method_name]
    chunking_method.chunk(st.session_state.docs)
    st.session_state.repo_chunked = True
    st.session_state.repo_indexed = False
    st.session_state.agent_wrapper = None
    st.success(f"✅ Chunking complete using {chunking_method.name} strategy")


# --- Step 3: Index Contents ---
def index_repo():
    if not st.session_state.repo_chunked:
        st.warning("Chunk the repo first.")
        return
    st.write("📇 Indexing documents...")
    st.session_state.search_method = SearchStrategyType[search_method_name]
    st.session_state.search_strategy = SearchStrategy()
    st.session_state.repo_indexed = True
    st.success(f"✅ Indexing complete using {st.session_state.search_method.name} search method")


# --- Step 4: Initialize Agent ---
def init_agent():
    if not st.session_state.repo_indexed:
        st.warning("Index the repo first.")
        return
    if st.session_state.agent_wrapper is None:
        st.write("🤖 Initializing AgentWrapper...")
        agent_wrapper = AgentWrapper(st.session_state.dtc_fastapi)
        agent_wrapper.setup(system_prompt)
        st.session_state.agent_wrapper = agent_wrapper
        st.success("✅ Agent initialized and ready for chat.")


# --- Buttons ---
st.subheader("⚙️ Workflow Controls")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.button("⬇️ Download Repo", on_click=download_repo, disabled=False)

with col2:
    st.button(
        "✂️ Chunk Documents",
        on_click=chunk_repo,
        disabled=not st.session_state.repo_downloaded,
    )

with col3:
    st.button(
        "📈 Index Contents",
        on_click=index_repo,
        disabled=not st.session_state.repo_chunked,
    )

with col4:
    st.button(
        "🤖 Initialize Agent",
        on_click=init_agent,
        disabled=not st.session_state.repo_indexed or st.session_state.agent_wrapper is not None,
    )

# --- Status Bar ---
status = []
if st.session_state.repo_downloaded:
    status.append("📦 Repo downloaded")
if st.session_state.repo_chunked:
    status.append("✂️ Docs chunked")
if st.session_state.repo_indexed:
    status.append("📈 Indexed")
if st.session_state.agent_wrapper:
    status.append("🤖 Agent ready")

if status:
    st.success(" → ".join(status))
else:
    st.info("⬇️ Start by downloading a repository.")


st.divider()


# --- Chat Section ---
if st.session_state.agent_wrapper:
    st.subheader("💬 Chat with your documentation")
    agent_wrapper = st.session_state.agent_wrapper
    agent_log = AgentLog()

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask your question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = asyncio.run(agent_wrapper.run(prompt))
                answer = response['conversation'][-1].parts[0].content
                st.markdown(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})
        
        agent_log.log_interaction_to_file(
            agent=agent_wrapper.agent,
            messages=response,
            source='streamlit_chat'
        )
else:
    st.info("⚙️ Complete all steps (Download → Chunk → Index → Initialize Agent) before chatting.")
