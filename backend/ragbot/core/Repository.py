"""Ingestion of a whole GitHub repository - source code as well as docs.

Files are downloaded once, filtered, and mirrored to an on-disk cache so that
later runs (and the agent's read_file/list_files tools) can work without touching
the network.
"""

import io
import json
import re
import hashlib
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
import frontmatter

from ragbot.core.TextChunker import TextChunker
from ragbot.core.CodeChunker import CodeChunker
from ragbot.core.settings import REPO_CACHE_DIR

CODELOAD_URL_RE = re.compile(
    r'github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/zip/refs/heads/(?P<branch>.+)$'
)

# An allowlist rather than a denylist: the failure mode of a missing extension is
# a file we skip, whereas a missing denylist entry means feeding a binary to the
# indexer.
INCLUDED_EXTENSIONS = {
    '.py', '.js', '.jsx', '.mjs', '.ts', '.tsx', '.go', '.rs', '.java', '.kt',
    '.rb', '.php', '.cs', '.c', '.h', '.cpp', '.cc', '.hpp', '.swift', '.scala',
    '.sh', '.bash', '.sql', '.yaml', '.yml', '.toml', '.json', '.html', '.css',
    '.scss', '.vue', '.svelte', '.md', '.mdx', '.rst', '.txt', '.ini', '.cfg',
}

INCLUDED_FILENAMES = {'dockerfile', 'makefile'}

EXCLUDED_DIRECTORIES = {
    '.git', 'node_modules', '.venv', 'venv', 'vendor', 'dist', 'build', 'target',
    '__pycache__', 'site-packages', '.next', '.nuxt', 'coverage', '.mypy_cache',
    '.pytest_cache', '.ruff_cache', 'logs',
}

EXCLUDED_FILENAMES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock',
    'uv.lock', 'cargo.lock', 'go.sum', 'composer.lock',
}

EXCLUDED_SUFFIXES = ('.min.js', '.min.css', '.map', '.lock')

MAX_FILE_BYTES = 200 * 1024
MARKDOWN_EXTENSIONS = ('.md', '.mdx')

# Beyond this, minsearch's brute-force cosine starts to drag; the UI warns rather
# than refusing, since it still works, just slower.
CHUNK_COUNT_WARNING_THRESHOLD = 5000


class Repository:

    def __init__(self, zip_path: str, cache_dir: Path = REPO_CACHE_DIR, repo_key: str = None):
        self.zip_path = zip_path
        self.cache_dir = Path(cache_dir)
        # A caller-supplied key is how local-folder uploads get a readable,
        # collision-free key (e.g. "local_myproject_a1b2c3d4") instead of the
        # opaque hash _slugify falls back to for a non-codeload "URL".
        self.repo_key = repo_key or self._slugify(zip_path)
        self.repo_dir = self.cache_dir / self.repo_key
        self.files_dictionary = []
        self.chunks = []
        self.text_chunker = TextChunker("")
        self.code_chunker = CodeChunker()
        self.processed_docs = 0
        self.skipped_docs = 0


    @staticmethod
    def _slugify(url: str) -> str:
        match = CODELOAD_URL_RE.search(url)
        if match:
            owner = match.group('owner')
            repo = match.group('repo')
            branch = re.sub(r'[^A-Za-z0-9_.-]+', '_', match.group('branch'))
            return f"{owner}_{repo}_{branch}"
        return hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]


    def blob_url_base(self):
        """Base GitHub URL for citations, derived from the ingested repo."""
        match = CODELOAD_URL_RE.search(self.zip_path)
        if not match:
            return None
        return (
            f"https://github.com/{match.group('owner')}/{match.group('repo')}"
            f"/blob/{match.group('branch')}/"
        )


    @staticmethod
    def repo_page_url(repo_url: str):
        """The repo's browsable GitHub page - repo_url itself is the codeload
        zip URL used to fetch it, which 404s if opened directly in a browser."""
        match = CODELOAD_URL_RE.search(repo_url)
        if not match:
            return None
        return f"https://github.com/{match.group('owner')}/{match.group('repo')}"


    @classmethod
    def list_cached_repos(cls, cache_dir: Path = REPO_CACHE_DIR):
        cache_dir = Path(cache_dir)
        if not cache_dir.exists():
            return []

        repos = []
        for repo_dir in sorted(cache_dir.iterdir()):
            meta_path = repo_dir / "_meta.json"
            if not meta_path.exists():
                continue
            try:
                with meta_path.open('r', encoding='utf-8') as f_in:
                    meta = json.load(f_in)
            except (json.JSONDecodeError, OSError):
                continue
            meta['repo_key'] = repo_dir.name
            repos.append(meta)

        repos.sort(key=lambda m: m.get('downloaded_at', ''), reverse=True)
        return repos


    @classmethod
    def should_include(cls, filename: str, size_bytes: int = 0) -> bool:
        """Decide whether a repo path is worth indexing."""
        path = Path(filename)
        parts = [p.lower() for p in path.parts]

        # The zip's top-level directory is "<repo>-<branch>/", never a real exclusion.
        if any(part in EXCLUDED_DIRECTORIES for part in parts[1:-1]):
            return False

        name = path.name.lower()
        if name in EXCLUDED_FILENAMES or name.startswith('.'):
            return False
        if name.endswith(EXCLUDED_SUFFIXES):
            return False
        if size_bytes > MAX_FILE_BYTES:
            return False

        if name in INCLUDED_FILENAMES:
            return True
        return path.suffix.lower() in INCLUDED_EXTENSIONS


    def _resolve_safe_path(self, filename: str) -> Path:
        # Zip entries are untrusted input - guard against zip-slip ("../..") writing outside repo_dir.
        target = (self.repo_dir / filename).resolve()
        repo_root = self.repo_dir.resolve()
        if repo_root not in target.parents and target != repo_root:
            raise ValueError(f"Unsafe path in zip entry: {filename}")
        return target


    def _save_to_disk(self, filename: str, content: str) -> None:
        target_path = self._resolve_safe_path(filename)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding='utf-8')


    def _write_meta(self, file_count: int) -> None:
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            'repo_url': self.zip_path,
            'downloaded_at': datetime.now(timezone.utc).isoformat(),
            'file_count': file_count,
        }
        with (self.repo_dir / "_meta.json").open('w', encoding='utf-8') as f_out:
            json.dump(meta, f_out, indent=2)


    def _build_file_record(self, filename: str, content: str) -> dict:
        """Normalise one file into the dict shape the rest of the pipeline expects."""
        if filename.lower().endswith(MARKDOWN_EXTENSIONS):
            # Markdown may carry frontmatter (title/description) worth indexing.
            post = frontmatter.loads(content)
            record = post.to_dict()
        else:
            record = {'content': content}

        record['filename'] = filename
        record['language'] = CodeChunker.language_for(filename) or ''
        record['size_bytes'] = len(content.encode('utf-8'))
        return record


    def get_repo_files(self):
        """Download the repo zip and extract every file worth indexing."""
        resp = requests.get(self.zip_path)

        if resp.status_code != 200:
            raise Exception(f"Failed to download repository: {resp.status_code}")

        return self._extract_zip(resp.content, strip_root=True)


    def load_from_zip_bytes(self, zip_bytes: bytes):
        """Extract an already-in-memory zip - e.g. one built client-side from a
        browser-uploaded local folder - without downloading anything. Shares the
        same filtering, zip-slip guard, and on-disk mirror as get_repo_files, so
        a local folder is indistinguishable from a downloaded one everywhere
        else in the pipeline.
        """
        return self._extract_zip(zip_bytes, strip_root=True)


    def _extract_zip(self, content: bytes, strip_root: bool):
        repository_data = []
        zf = zipfile.ZipFile(io.BytesIO(content))

        for file_info in zf.infolist():
            if file_info.is_dir():
                continue

            filename = file_info.filename
            if not self.should_include(filename, file_info.file_size):
                continue

            try:
                with zf.open(file_info) as f_in:
                    file_content = f_in.read().decode('utf-8', errors='ignore')

                # Drop the zip's leading directory ("<repo>-<branch>/" for a
                # GitHub download, "<folder-name>/" for an uploaded folder) so
                # cached paths match the repo either way.
                relative_name = self._strip_root(filename) if strip_root else filename
                self._save_to_disk(relative_name, file_content)
                repository_data.append(self._build_file_record(relative_name, file_content))
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                continue

        zf.close()
        self.files_dictionary = repository_data
        self._write_meta(len(repository_data))
        return repository_data


    @staticmethod
    def _strip_root(filename: str) -> str:
        parts = filename.split('/', 1)
        return parts[1] if len(parts) == 2 else filename


    def load_cached_repo_files(self):
        """Load a previously downloaded repo from disk, skipping the network fetch."""
        if not self.repo_dir.exists():
            raise FileNotFoundError(f"No cached repo found at {self.repo_dir}")

        repository_data = []
        for path in sorted(self.repo_dir.rglob('*')):
            if not path.is_file() or path.name == '_meta.json':
                continue

            filename = path.relative_to(self.repo_dir).as_posix()
            if not self.should_include(filename, path.stat().st_size):
                continue

            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                repository_data.append(self._build_file_record(filename, content))
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                continue

        self.files_dictionary = repository_data
        return repository_data


    def chunk(self, strategy, on_progress=None):
        """Chunk every ingested file, returning a flat list of chunk dicts.

        Builds a new list rather than mutating files_dictionary in place, and merges
        each file's metadata into its chunks so filename/language survive into the
        index - citations depend on it.

        on_progress(done, total), if given, is called once per file (fast in
        practice - see the README's benchmarks - but a large repo's file count
        can still take a visible moment to get through).
        """
        from ragbot.core.ChunkingStrategy import ChunkingStrategy

        self.processed_docs = 0
        self.skipped_docs = 0
        all_chunks = []
        total = len(self.files_dictionary)

        for i, doc in enumerate(self.files_dictionary):
            content = doc.get('content')
            if not content or not content.strip():
                self.skipped_docs += 1
                if on_progress:
                    on_progress(i + 1, total)
                continue

            self.processed_docs += 1
            file_metadata = {k: v for k, v in doc.items() if k != 'content'}
            filename = doc.get('filename', '')

            for chunk in self._chunk_one(content, filename, doc, strategy, ChunkingStrategy):
                merged = dict(file_metadata)
                merged.update(chunk)
                all_chunks.append(self._normalise(merged))

            if on_progress:
                on_progress(i + 1, total)

        self.chunks = all_chunks
        return all_chunks


    @staticmethod
    def _normalise(chunk):
        """Guarantee the fields the index and citations rely on always exist.

        The simpler strategies (paragraph, character, LLM) don't produce symbols or
        line ranges, and minsearch would otherwise index None.
        """
        chunk.setdefault('body', chunk.get('chunk', ''))
        chunk.setdefault('symbol', '')
        chunk.setdefault('kind', '')
        chunk.setdefault('method', '')
        chunk.setdefault('start_line', None)
        chunk.setdefault('end_line', None)
        for field in ('symbol', 'kind', 'method', 'filename', 'language'):
            if chunk.get(field) is None:
                chunk[field] = ''
        return chunk


    def _chunk_one(self, content, filename, doc, strategy, ChunkingStrategy):
        """Chunk a single file according to the selected strategy.

        Tags every chunk with the concrete method actually used - under AUTO
        that varies per file (markdown vs. code), so a chunk can't recover
        which one ran from the repo-level strategy name alone. Matches
        ChunkingStrategy's own member names, so the UI can reuse the same
        name -> label mapping /api/config already returns.
        """
        is_markdown = filename.lower().endswith(MARKDOWN_EXTENSIONS)
        language = doc.get('language') or CodeChunker.language_for(filename)

        if strategy == ChunkingStrategy.AUTO:
            # A repo holds both code and prose, so dispatch per file rather than
            # forcing one strategy across everything.
            if is_markdown:
                chunks, method = self._markdown_chunks(content, filename), ChunkingStrategy.MARKDOWN.name
            else:
                chunks, method = self.code_chunker.chunk_file(content, filename, language), ChunkingStrategy.AST.name
        elif strategy == ChunkingStrategy.AST:
            chunks, method = self.code_chunker.chunk_file(content, filename, language), ChunkingStrategy.AST.name
        elif strategy == ChunkingStrategy.MARKDOWN:
            chunks, method = self._markdown_chunks(content, filename), ChunkingStrategy.MARKDOWN.name
        elif strategy == ChunkingStrategy.PARAGRAPH:
            chunks, method = self.text_chunker.chunk_by_paragraphs(content), ChunkingStrategy.PARAGRAPH.name
        elif strategy == ChunkingStrategy.CHARACTER:
            chunks, method = self.text_chunker.sliding_window(content, 2000, 1000), ChunkingStrategy.CHARACTER.name
        elif strategy == ChunkingStrategy.LLM:
            chunks = [{'chunk': s} for s in self.text_chunker.intelligent_chunking(content)]
            method = ChunkingStrategy.LLM.name
        else:
            raise ValueError(f"Unsupported chunking strategy: {strategy}")

        for chunk in chunks:
            chunk['method'] = method
        return chunks


    def _markdown_chunks(self, content, filename):
        chunks = self.text_chunker.split_markdown_by_level(content)
        if not chunks:
            chunks = self.text_chunker.chunk_by_paragraphs(content)
        return chunks


    def language_stats(self):
        counts = Counter(
            (doc.get('language') or Path(doc['filename']).suffix or 'other')
            for doc in self.files_dictionary
        )
        return dict(counts.most_common())


    def print_summary(self):
        print(f"Processed documents: {self.processed_docs}")
        print(f"Skipped documents: {self.skipped_docs}")
        print(f"Total chunks created: {len(self.chunks)}")
