import asyncio

import streamlit as st

from src.Repository import Repository, CHUNK_COUNT_WARNING_THRESHOLD
from src.ChunkingStrategy import ChunkingStrategy
from src.SearchStrategy import SearchStrategy, SearchStrategyType
from src.Embeddings import get_embedder
from src.AgentWrapper import AgentWrapper
from src.AgentLog import AgentLog
from src.Prompts import Prompts

# --- Page config ---
st.set_page_config(page_title="AI Code Assistant", page_icon="🤖", layout="centered")
st.title("🤖 AI Code Assistant")
st.caption("Ask questions about any GitHub repository's code and documentation")


# --- User Inputs ---
repo_url = st.text_input(
    "🔗 Enter GitHub repository URL:",
    "https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main"
)

cached_repos = Repository.list_cached_repos()
cached_repo_options = {
    f"{repo['repo_url']} — {repo['file_count']} files ({repo['downloaded_at'][:19]} UTC)": repo
    for repo in cached_repos
}
NO_CACHED_REPO_LABEL = "-- select a cached repo --"

selected_cached_label = NO_CACHED_REPO_LABEL
if cached_repo_options:
    selected_cached_label = st.selectbox(
        "📂 Or load a previously downloaded repo (skips re-downloading):",
        options=[NO_CACHED_REPO_LABEL] + list(cached_repo_options.keys()),
    )

with st.expander("⚙️ Advanced settings"):
    chunking_method_name = st.selectbox(
        "🧩 Chunking Method:",
        options=[c.name for c in ChunkingStrategy],
        index=0,
        help="AUTO picks per file: AST for code, headings for markdown, line windows otherwise.",
    )

    search_method_name = st.selectbox(
        "🔍 Search Method:",
        options=[s.name for s in SearchStrategyType],
        index=2,
        help="HYBRID fuses keyword and vector results with reciprocal rank fusion.",
    )

    system_prompt = st.text_area(
        "📝 System Prompt (for agent):",
        value=Prompts.SYSTEM_PROMPT.strip(),
        height=200,
    )


# --- Initialize session state ---
defaults = {
    "repository": None,
    "chunks": None,
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


def _reset_downstream():
    st.session_state.repo_chunked = False
    st.session_state.repo_indexed = False
    st.session_state.agent_wrapper = None
    st.session_state.chunks = None
    st.session_state.messages = []


def _report_ingestion(repository, files):
    st.success(f"✅ {len(files)} files ingested")
    stats = repository.language_stats()
    if stats:
        summary = ", ".join(f"{lang or 'other'}: {count}" for lang, count in list(stats.items())[:10])
        st.caption(f"Languages — {summary}")


# --- Step 1: Download Repo ---
def download_repo():
    st.write(f"📦 Downloading repository from: {repo_url}")
    repository = Repository(repo_url)
    files = repository.get_repo_files()
    st.session_state.repository = repository
    st.session_state.repo_downloaded = True
    _reset_downstream()
    _report_ingestion(repository, files)


# --- Step 1b: Load Cached Repo ---
def load_cached_repo():
    if selected_cached_label == NO_CACHED_REPO_LABEL:
        st.warning("Select a cached repo first.")
        return
    repo_meta = cached_repo_options[selected_cached_label]
    st.write(f"📂 Loading cached repository: {repo_meta['repo_url']}")
    repository = Repository(repo_meta['repo_url'])
    files = repository.load_cached_repo_files()
    st.session_state.repository = repository
    st.session_state.repo_downloaded = True
    _reset_downstream()
    _report_ingestion(repository, files)


# --- Step 2: Chunk Documents ---
def chunk_repo():
    if not st.session_state.repository:
        st.warning("Download the repo first.")
        return
    st.write("🔄 Chunking repository...")
    chunking_method = ChunkingStrategy[chunking_method_name]
    chunks = st.session_state.repository.chunk(chunking_method)
    st.session_state.chunks = chunks
    st.session_state.repo_chunked = True
    st.session_state.repo_indexed = False
    st.session_state.agent_wrapper = None
    st.success(f"✅ {len(chunks)} chunks created using {chunking_method.name}")

    if len(chunks) > CHUNK_COUNT_WARNING_THRESHOLD:
        st.warning(
            f"⚠️ {len(chunks)} chunks exceeds the ~{CHUNK_COUNT_WARNING_THRESHOLD} "
            "comfort limit for in-memory search. Indexing and queries will be slow."
        )


# --- Step 3: Index Contents ---
def index_repo():
    if not st.session_state.repo_chunked:
        st.warning("Chunk the repo first.")
        return
    embedder = get_embedder()
    st.write(f"📇 Indexing with {embedder.name}...")
    st.session_state.search_method = SearchStrategyType[search_method_name]
    search_strategy = SearchStrategy(embedder=embedder)

    # Build the vector index now rather than on the first query, so the embedding
    # cost (and any cache saving) is visible here instead of stalling the chat.
    if st.session_state.search_method in (SearchStrategyType.VECTOR, SearchStrategyType.HYBRID):
        with st.spinner("Embedding chunks..."):
            search_strategy.searcher._get_vector_index(st.session_state.chunks)

    st.session_state.search_strategy = search_strategy
    st.session_state.repo_indexed = True
    st.success(f"✅ Indexed for {st.session_state.search_method.name} search")

    if getattr(embedder, 'last_hits', 0) or getattr(embedder, 'last_misses', 0):
        st.caption(
            f"Embedding cache — {embedder.last_hits} reused, {embedder.last_misses} newly embedded"
        )


# --- Step 4: Initialize Agent ---
def init_agent():
    if not st.session_state.repo_indexed:
        st.warning("Index the repo first.")
        return
    if st.session_state.agent_wrapper is None:
        st.write("🤖 Initializing agent...")
        repository = st.session_state.repository
        agent_wrapper = AgentWrapper(
            st.session_state.chunks,
            search_strategy=st.session_state.search_strategy,
            search_method=st.session_state.search_method,
            repo_dir=repository.repo_dir,
        )
        # Only append GitHub-link guidance when the URL is parseable.
        instructions = system_prompt
        if repository.blob_url_base():
            instructions += Prompts.CITATION_SUFFIX_FORMAT.format(
                blob_url_base=repository.blob_url_base()
            )
        agent_wrapper.setup(instructions)
        st.session_state.agent_wrapper = agent_wrapper
        st.success("✅ Agent ready.")


# --- Buttons ---
st.subheader("⚙️ Workflow Controls")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.button("⬇️ Download Repo", on_click=download_repo, disabled=False)

with col2:
    st.button(
        "📂 Load Cached Repo",
        on_click=load_cached_repo,
        disabled=not cached_repo_options,
    )

with col3:
    st.button(
        "✂️ Chunk Documents",
        on_click=chunk_repo,
        disabled=not st.session_state.repo_downloaded,
    )

with col4:
    st.button(
        "📈 Index Contents",
        on_click=index_repo,
        disabled=not st.session_state.repo_chunked,
    )

with col5:
    st.button(
        "🤖 Initialize Agent",
        on_click=init_agent,
        disabled=not st.session_state.repo_indexed or st.session_state.agent_wrapper is not None,
    )

# --- Status Bar ---
status = []
if st.session_state.repo_downloaded:
    status.append("📦 Repo ingested")
if st.session_state.repo_chunked:
    status.append("✂️ Chunked")
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
    st.subheader("💬 Chat with the codebase")
    agent_wrapper = st.session_state.agent_wrapper
    agent_log = AgentLog()

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask about the code..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = asyncio.run(agent_wrapper.run(prompt))
                answer = response['response']
                st.markdown(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})

        agent_log.log_interaction_to_file(
            agent=agent_wrapper.agent,
            messages=response['conversation'],
            source='streamlit_chat'
        )
else:
    st.info("⚙️ Complete all steps (Download → Chunk → Index → Initialize Agent) before chatting.")
