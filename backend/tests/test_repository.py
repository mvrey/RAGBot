import io
import json
import zipfile

import pytest

from ragbot.core.Repository import Repository, MAX_FILE_BYTES
from ragbot.core.ChunkingStrategy import ChunkingStrategy


def _build_zip(entries: dict) -> bytes:
    """entries: {path-within-zip: text-content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for path, content in entries.items():
            zf.writestr(path, content)
    return buf.getvalue()


class TestFileSelection:

    @pytest.mark.parametrize("filename", [
        "repo-main/src/app.py",
        "repo-main/main.go",
        "repo-main/README.md",
        "repo-main/pyproject.toml",
        "repo-main/Dockerfile",
        "repo-main/web/index.html",
    ])
    def test_included(self, filename):
        assert Repository.should_include(filename, 100)

    @pytest.mark.parametrize("filename", [
        "repo-main/node_modules/lib/index.js",
        "repo-main/.venv/lib/site.py",
        "repo-main/dist/bundle.js",
        "repo-main/__pycache__/mod.py",
        "repo-main/logs/run.json",
    ])
    def test_excluded_directories(self, filename):
        assert not Repository.should_include(filename, 100)

    @pytest.mark.parametrize("filename", [
        "repo-main/package-lock.json",
        "repo-main/uv.lock",
        "repo-main/go.sum",
        "repo-main/app.min.js",
        "repo-main/style.min.css",
        "repo-main/bundle.js.map",
    ])
    def test_excluded_files(self, filename):
        assert not Repository.should_include(filename, 100)

    @pytest.mark.parametrize("filename", [
        "repo-main/logo.png",
        "repo-main/data.bin",
        "repo-main/archive.zip",
    ])
    def test_binaries_are_not_allowlisted(self, filename):
        assert not Repository.should_include(filename, 100)

    def test_oversized_files_are_skipped(self):
        assert not Repository.should_include("repo-main/huge.py", MAX_FILE_BYTES + 1)

    def test_dotfiles_are_skipped(self):
        assert not Repository.should_include("repo-main/.env", 10)

    def test_repo_root_directory_is_not_treated_as_an_exclusion(self):
        # The zip's root is "<repo>-<branch>/" and may collide with an excluded name.
        assert Repository.should_include("build-main/src/app.py", 100)


class TestSlugAndUrls:

    URL = "https://codeload.github.com/owner/repo/zip/refs/heads/main"

    def test_slug_from_github_url(self):
        assert Repository._slugify(self.URL) == "owner_repo_main"

    def test_slug_falls_back_to_hash(self):
        slug = Repository._slugify("https://example.com/archive.zip")
        assert slug and "/" not in slug

    def test_blob_url_base(self):
        repo = Repository(self.URL)
        assert repo.blob_url_base() == "https://github.com/owner/repo/blob/main/"

    def test_blob_url_base_is_none_for_unrecognised_urls(self):
        assert Repository("https://example.com/x.zip").blob_url_base() is None

    def test_branch_with_slash_is_slugified(self):
        slug = Repository._slugify(
            "https://codeload.github.com/o/r/zip/refs/heads/feature/new-thing"
        )
        assert "/" not in slug


class TestChunking:

    def _repo(self, tmp_path, files):
        repo = Repository("https://codeload.github.com/o/r/zip/refs/heads/main", cache_dir=tmp_path)
        repo.files_dictionary = [
            repo._build_file_record(name, content) for name, content in files.items()
        ]
        return repo

    def test_auto_dispatches_per_file_type(self, tmp_path):
        repo = self._repo(tmp_path, {
            "app.py": "def handler():\n    return 1\n",
            "README.md": "# Title\n\n## Setup\n\nRun it.\n\n## Usage\n\nUse it.\n",
        })

        chunks = repo.chunk(ChunkingStrategy.AUTO)
        kinds = {c['filename']: {c2['kind'] for c2 in chunks if c2['filename'] == c['filename']}
                 for c in chunks}

        assert 'function_definition' in kinds['app.py']
        assert 'section' in kinds['README.md']

    def test_every_chunk_keeps_its_filename(self, tmp_path):
        # Regression: paragraph/markdown chunkers used to drop parent metadata,
        # which silently broke citations.
        repo = self._repo(tmp_path, {
            "a.py": "def f():\n    return 1\n",
            "b.md": "# T\n\n## S\n\nbody\n",
        })

        for strategy in (ChunkingStrategy.AUTO, ChunkingStrategy.PARAGRAPH, ChunkingStrategy.CHARACTER):
            chunks = repo.chunk(strategy)
            assert chunks
            assert all(c.get('filename') for c in chunks), f"{strategy} dropped filename"

    def test_originals_are_not_left_in_the_chunk_list(self, tmp_path):
        # Regression: chunking used to extend the list it was iterating, leaving
        # unchunked originals in the index alongside their own chunks.
        source = "def f():\n    return 1\n\ndef g():\n    return 2\n"
        repo = self._repo(tmp_path, {"a.py": source})

        chunks = repo.chunk(ChunkingStrategy.AUTO)

        assert all(c.get('body') != source for c in chunks)

    def test_chunk_counts_are_stable_across_runs(self, tmp_path):
        repo = self._repo(tmp_path, {"a.py": "def f():\n    return 1\n"})

        first = len(repo.chunk(ChunkingStrategy.AUTO))
        second = len(repo.chunk(ChunkingStrategy.AUTO))

        assert first == second

    def test_normalised_fields_are_never_none(self, tmp_path):
        repo = self._repo(tmp_path, {"a.txt": "just some text\n"})

        for chunk in repo.chunk(ChunkingStrategy.PARAGRAPH):
            assert chunk['symbol'] is not None
            assert chunk['kind'] is not None
            assert chunk['language'] is not None

    def test_empty_files_are_skipped(self, tmp_path):
        repo = self._repo(tmp_path, {"empty.py": "", "real.py": "def f():\n    pass\n"})

        repo.chunk(ChunkingStrategy.AUTO)

        assert repo.skipped_docs == 1
        assert repo.processed_docs == 1

    def test_on_progress_reports_one_call_per_file_including_skipped(self, tmp_path):
        repo = self._repo(tmp_path, {
            "empty.py": "",
            "a.py": "def f():\n    return 1\n",
            "b.py": "def g():\n    return 2\n",
        })
        calls = []

        repo.chunk(ChunkingStrategy.AUTO, on_progress=lambda done, total: calls.append((done, total)))

        assert calls == [(1, 3), (2, 3), (3, 3)]


class TestDiskCache:

    def test_round_trip(self, tmp_path):
        repo = Repository("https://codeload.github.com/o/r/zip/refs/heads/main", cache_dir=tmp_path)
        repo._save_to_disk("src/app.py", "def f():\n    return 1\n")
        repo._write_meta(1)

        reloaded = Repository(
            "https://codeload.github.com/o/r/zip/refs/heads/main", cache_dir=tmp_path
        ).load_cached_repo_files()

        assert [f['filename'] for f in reloaded] == ["src/app.py"]
        assert reloaded[0]['language'] == 'python'

    def test_listing_reports_cached_repos(self, tmp_path):
        repo = Repository("https://codeload.github.com/o/r/zip/refs/heads/main", cache_dir=tmp_path)
        repo._save_to_disk("a.py", "x = 1\n")
        repo._write_meta(1)

        listed = Repository.list_cached_repos(cache_dir=tmp_path)

        assert len(listed) == 1
        assert listed[0]['repo_key'] == 'o_r_main'

    def test_missing_cache_raises(self, tmp_path):
        repo = Repository("https://codeload.github.com/o/r/zip/refs/heads/main", cache_dir=tmp_path)

        with pytest.raises(FileNotFoundError):
            repo.load_cached_repo_files()

    @pytest.mark.parametrize("evil", ["../escape.py", "../../etc/passwd", "a/../../b.py"])
    def test_zip_slip_is_rejected(self, tmp_path, evil):
        repo = Repository("https://codeload.github.com/o/r/zip/refs/heads/main", cache_dir=tmp_path)

        with pytest.raises(ValueError):
            repo._resolve_safe_path(evil)

    def test_strip_root_removes_the_zip_prefix(self):
        assert Repository._strip_root("repo-main/src/app.py") == "src/app.py"
        assert Repository._strip_root("app.py") == "app.py"


class TestRepoKeyOverride:

    def test_explicit_repo_key_is_used_instead_of_slugifying(self, tmp_path):
        repo = Repository("local:myproject", cache_dir=tmp_path, repo_key="local_myproject_ab12")

        assert repo.repo_key == "local_myproject_ab12"
        assert repo.repo_dir == tmp_path / "local_myproject_ab12"

    def test_no_repo_key_falls_back_to_slugify(self, tmp_path):
        repo = Repository("https://codeload.github.com/o/r/zip/refs/heads/main", cache_dir=tmp_path)

        assert repo.repo_key == "o_r_main"

    def test_local_pseudo_url_has_no_blob_url_base(self, tmp_path):
        repo = Repository("local:myproject", cache_dir=tmp_path, repo_key="local_myproject_ab12")

        assert repo.blob_url_base() is None


class TestLoadFromZipBytes:

    def _repo(self, tmp_path):
        return Repository("local:myproject", cache_dir=tmp_path, repo_key="local_myproject_ab12")

    def test_extracts_included_files_and_mirrors_them_to_disk(self, tmp_path):
        repo = self._repo(tmp_path)
        zip_bytes = _build_zip({
            "myproject/src/app.py": "def f(): pass",
            "myproject/README.md": "# hi",
        })

        files = repo.load_from_zip_bytes(zip_bytes)

        names = {f['filename'] for f in files}
        assert names == {"src/app.py", "README.md"}
        assert (repo.repo_dir / "src" / "app.py").read_text(encoding='utf-8') == "def f(): pass"

    def test_filters_excluded_files_the_same_as_a_download(self, tmp_path):
        repo = self._repo(tmp_path)
        zip_bytes = _build_zip({
            "myproject/src/app.py": "def f(): pass",
            "myproject/node_modules/lib/index.js": "module.exports = {}",
            "myproject/package-lock.json": "{}",
        })

        files = repo.load_from_zip_bytes(zip_bytes)

        assert {f['filename'] for f in files} == {"src/app.py"}

    def test_writes_meta_with_the_pseudo_url_as_repo_url(self, tmp_path):
        repo = self._repo(tmp_path)
        repo.load_from_zip_bytes(_build_zip({"myproject/a.py": "x = 1"}))

        meta = json.loads((repo.repo_dir / "_meta.json").read_text(encoding='utf-8'))
        assert meta['repo_url'] == "local:myproject"
        assert meta['file_count'] == 1

    def test_traversal_past_the_allowlist_is_filtered(self, tmp_path):
        repo = self._repo(tmp_path)
        # No matching extension/filename, so this never reaches the zip-slip
        # guard at all - it's rejected by should_include() first.
        zip_bytes = _build_zip({"../../etc/passwd": "malicious"})

        assert repo.load_from_zip_bytes(zip_bytes) == []

    def test_traversal_with_an_allowed_extension_hits_the_zip_slip_guard(self, tmp_path):
        repo = self._repo(tmp_path)
        # _strip_root() drops the first path segment (the zip's top-level
        # folder), which incidentally neutralises a single "../" - so this
        # needs a second one to actually still be a traversal afterwards,
        # reaching should_include() (".py" passes) and then only being
        # stopped by _resolve_safe_path() refusing to write outside repo_dir.
        zip_bytes = _build_zip({"myproject/../../escape.py": "malicious = True"})

        assert repo.load_from_zip_bytes(zip_bytes) == []
        assert not (tmp_path / "escape.py").exists()
        assert not (tmp_path / "escape.py").exists()
