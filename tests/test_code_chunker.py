import pytest

from src.CodeChunker import CodeChunker


@pytest.fixture
def chunker():
    return CodeChunker()


PYTHON_SOURCE = '''import os

CONSTANT = 42

def top_level():
    """Docstring."""
    return 1

@decorator
def decorated():
    return 2

class Widget:
    def render(self):
        return "x"
'''


def test_python_functions_become_chunks(chunker):
    chunks = chunker.chunk_file(PYTHON_SOURCE, "src/widget.py")
    symbols = {c['symbol'] for c in chunks}

    assert 'top_level' in symbols
    assert 'decorated' in symbols, "decorated_definition should resolve to the inner name"
    assert 'Widget' in symbols


def test_chunks_carry_location_metadata(chunker):
    chunks = chunker.chunk_file(PYTHON_SOURCE, "src/widget.py")

    for chunk in chunks:
        assert chunk['filename'] == "src/widget.py"
        assert chunk['language'] == 'python'
        assert chunk['start_line'] >= 1
        assert chunk['end_line'] >= chunk['start_line']


def test_decorator_is_included_in_the_chunk_body(chunker):
    chunks = chunker.chunk_file(PYTHON_SOURCE, "src/widget.py")
    decorated = next(c for c in chunks if c['symbol'] == 'decorated')

    assert '@decorator' in decorated['body']


def test_module_level_code_is_captured(chunker):
    chunks = chunker.chunk_file(PYTHON_SOURCE, "src/widget.py")
    module_bodies = " ".join(c['body'] for c in chunks if c['kind'] == 'module_level')

    # Imports and constants answer dependency questions, so they must be indexed.
    assert 'import os' in module_bodies
    assert 'CONSTANT' in module_bodies


def test_chunk_text_includes_a_context_header(chunker):
    chunk = chunker.chunk_file(PYTHON_SOURCE, "src/widget.py")[0]

    assert chunk['chunk'].startswith('# src/widget.py | python |')
    assert chunk['body'] in chunk['chunk']


def _class_of_size(method_count):
    methods = "\n".join(
        f"    def method_{i}(self):\n        return {i}\n" for i in range(method_count)
    )
    return f"class Big:\n{methods}"


def test_large_class_splits_into_qualified_methods(chunker):
    # 60 methods is ~180 lines, comfortably past the 120-line split threshold.
    chunks = chunker.chunk_file(_class_of_size(60), "big.py")
    symbols = {c['symbol'] for c in chunks}

    assert 'Big.method_0' in symbols, "methods of a split class should be qualified"
    assert 'Big.method_59' in symbols
    assert 'Big' in symbols, "the class header should survive as its own chunk"


def test_split_class_header_precedes_its_methods(chunker):
    chunks = chunker.chunk_file(_class_of_size(60), "big.py")
    by_symbol = {c['symbol']: c for c in chunks}

    assert by_symbol['Big']['end_line'] < by_symbol['Big.method_0']['start_line']


def test_small_class_stays_whole(chunker):
    chunks = chunker.chunk_file(PYTHON_SOURCE, "src/widget.py")
    widget = [c for c in chunks if c['symbol'].startswith('Widget')]

    assert len(widget) == 1, "a small class reads better as one chunk"


@pytest.mark.parametrize("language,filename,source,expected_symbol", [
    ('go', 'main.go', 'package main\n\nfunc Add(a int) int { return a }\n', 'Add'),
    ('go', 'main.go', 'package main\n\ntype Server struct { Port int }\n', 'Server'),
    ('rust', 'lib.rs', 'fn helper() -> i32 { 1 }\n', 'helper'),
    ('java', 'A.java', 'class A { void run() {} }\n', 'A'),
    ('javascript', 'a.js', 'function greet() { return 1; }\n', 'greet'),
    ('ruby', 'a.rb', 'def run\n  1\nend\n', 'run'),
])
def test_multi_language_symbol_extraction(chunker, language, filename, source, expected_symbol):
    chunks = chunker.chunk_file(source, filename)

    assert expected_symbol in {c['symbol'] for c in chunks}


def test_unsupported_language_falls_back_to_windows(chunker):
    # c_sharp has no grammar in the bundled language pack.
    chunks = chunker.chunk_file("class C {\n  void M() {}\n}\n", "Program.cs")

    assert chunks
    assert all(c['kind'] == 'window' for c in chunks)


def test_malformed_source_does_not_raise(chunker):
    chunks = chunker.chunk_file("def broken(:\n  ???\nclass ", "bad.py")

    # One unparseable file must never sink ingestion of a whole repo.
    assert chunks
    assert all(c['filename'] == 'bad.py' for c in chunks)


def test_empty_file_yields_no_chunks(chunker):
    assert chunker.chunk_file("", "empty.py") == []


def test_language_detection():
    assert CodeChunker.language_for("a/b/c.py") == 'python'
    assert CodeChunker.language_for("Main.GO") == 'go'
    assert CodeChunker.language_for("notes.md") is None
