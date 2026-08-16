"""AST-aware chunking for source code, backed by tree-sitter.

A chunk is one function/class/method, kept whole so its signature and docstring
travel with its body. Anything we cannot parse (unsupported language, syntax
errors, oversized nodes) degrades to overlapping line windows rather than failing
ingestion - a single bad file must never sink a whole repository.
"""

LANGUAGE_BY_EXTENSION = {
    '.py': 'python',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.mjs': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'tsx',
    '.go': 'go',
    '.rs': 'rust',
    '.java': 'java',
    '.kt': 'kotlin',
    '.rb': 'ruby',
    '.php': 'php',
    '.c': 'c',
    '.h': 'c',
    '.cpp': 'cpp',
    '.cc': 'cpp',
    '.hpp': 'cpp',
    '.cs': 'c_sharp',
    '.swift': 'swift',
    '.scala': 'scala',
    '.sh': 'bash',
    '.bash': 'bash',
}

# Node types worth emitting as their own chunk. Names differ per grammar, so these
# were read off the actual parsers rather than assumed.
CHUNK_NODE_TYPES = {
    'python': {'function_definition', 'class_definition', 'decorated_definition'},
    'javascript': {'function_declaration', 'class_declaration', 'method_definition', 'generator_function_declaration'},
    'typescript': {'function_declaration', 'class_declaration', 'method_definition', 'interface_declaration', 'abstract_class_declaration'},
    'tsx': {'function_declaration', 'class_declaration', 'method_definition', 'interface_declaration'},
    'go': {'function_declaration', 'method_declaration', 'type_declaration'},
    'rust': {'function_item', 'impl_item', 'struct_item', 'trait_item', 'enum_item'},
    'java': {'class_declaration', 'method_declaration', 'interface_declaration', 'constructor_declaration'},
    'kotlin': {'function_declaration', 'class_declaration', 'object_declaration'},
    'ruby': {'method', 'class', 'module', 'singleton_method'},
    'php': {'function_definition', 'class_declaration', 'method_declaration'},
    'c': {'function_definition', 'struct_specifier'},
    'cpp': {'function_definition', 'class_specifier', 'struct_specifier'},
    'swift': {'function_declaration', 'class_declaration', 'protocol_declaration'},
    'scala': {'function_definition', 'class_definition', 'object_definition', 'trait_definition'},
    'bash': {'function_definition'},
}

# Chunk nodes that hold further definitions worth splitting out on their own.
CONTAINER_NODE_TYPES = {
    'python': {'class_definition'},
    'javascript': {'class_declaration'},
    'typescript': {'class_declaration', 'abstract_class_declaration'},
    'tsx': {'class_declaration'},
    'rust': {'impl_item', 'trait_item'},
    'java': {'class_declaration', 'interface_declaration'},
    'kotlin': {'class_declaration', 'object_declaration'},
    'ruby': {'class', 'module'},
    'php': {'class_declaration'},
    'cpp': {'class_specifier'},
    'swift': {'class_declaration', 'protocol_declaration'},
    'scala': {'class_definition', 'object_definition', 'trait_definition'},
}

# A container is only split apart when it is big enough to be worth it; small
# classes read better as a single chunk.
MAX_CHUNK_LINES = 120
WINDOW_LINES = 80
WINDOW_OVERLAP_LINES = 15


class CodeChunker:

    def __init__(self, max_chunk_lines: int = MAX_CHUNK_LINES):
        self.max_chunk_lines = max_chunk_lines
        self._parsers = {}

    @staticmethod
    def language_for(filename: str):
        """Map a filename to a tree-sitter language name, or None if unknown."""
        lowered = filename.lower()
        if lowered.endswith('dockerfile') or lowered.endswith('makefile'):
            return None
        for extension, language in LANGUAGE_BY_EXTENSION.items():
            if lowered.endswith(extension):
                return language
        return None

    def _get_parser(self, language: str):
        """Return a cached parser, or None when the grammar is unavailable.

        Not every grammar ships with tree-sitter-language-pack (c_sharp, for one),
        so an unavailable language is a normal outcome, not an error.
        """
        if language not in self._parsers:
            try:
                from tree_sitter_language_pack import get_parser
                self._parsers[language] = get_parser(language)
            except Exception:
                self._parsers[language] = None
        return self._parsers[language]

    def chunk_file(self, content: str, filename: str, language: str = None):
        """Chunk one source file into a list of chunk dicts."""
        language = language or self.language_for(filename)
        parser = self._get_parser(language) if language else None

        if parser is None:
            return self._window_chunks(content, filename, language)

        try:
            tree = parser.parse(content.encode('utf-8'))
        except Exception:
            return self._window_chunks(content, filename, language)

        lines = content.splitlines()
        chunk_types = CHUNK_NODE_TYPES.get(language, set())
        container_types = CONTAINER_NODE_TYPES.get(language, set())

        spans = []
        self._collect(tree.root_node, chunk_types, container_types, lines, [], spans)

        if not spans:
            return self._window_chunks(content, filename, language)

        spans.extend(self._gap_spans(spans, lines))
        spans.sort(key=lambda s: s['start_line'])

        return [self._build_chunk(s, lines, filename, language) for s in spans]

    def _collect(self, node, chunk_types, container_types, lines, symbol_path, spans):
        """Walk the tree, recording spans for definition nodes."""
        for child in node.children:
            if child.type not in chunk_types:
                # Keep descending: JS classes wrap members in a class_body, Rust
                # impls in a declaration_list, and so on.
                self._collect(child, chunk_types, container_types, lines, symbol_path, spans)
                continue

            name = self._node_name(child)
            qualified = symbol_path + [name] if name else symbol_path
            span_lines = child.end_point[0] - child.start_point[0] + 1
            is_container = child.type in container_types

            if is_container and span_lines > self.max_chunk_lines:
                # Emit the class header (up to its first member) then split members out.
                inner = []
                self._collect(child, chunk_types, container_types, lines, qualified, inner)
                if inner:
                    header_end = min(s['start_line'] for s in inner) - 1
                    if header_end >= child.start_point[0] + 1:
                        spans.append({
                            'start_line': child.start_point[0] + 1,
                            'end_line': header_end,
                            'symbol': '.'.join(qualified),
                            'kind': child.type,
                        })
                    spans.extend(inner)
                    continue

            spans.append({
                'start_line': child.start_point[0] + 1,
                'end_line': child.end_point[0] + 1,
                'symbol': '.'.join(qualified),
                'kind': child.type,
            })

    def _node_name(self, node):
        named = node.child_by_field_name('name')
        if named is not None:
            return named.text.decode('utf-8', errors='ignore')

        # Some grammars wrap the named node: Python decorators hold the real
        # definition, Go's type_declaration holds a type_spec, C nests declarators.
        wrapper_suffixes = ('_definition', '_declaration', '_item', '_spec', '_declarator')
        for child in node.children:
            if child.type.endswith(wrapper_suffixes):
                nested = self._node_name(child)
                if nested:
                    return nested
        for child in node.children:
            if child.type in ('type_identifier', 'identifier', 'constant', 'field_identifier'):
                return child.text.decode('utf-8', errors='ignore')
        return None

    def _gap_spans(self, spans, lines):
        """Capture top-level code between definitions (imports, constants, config).

        Dependency and configuration questions are usually answered by exactly this
        material, so dropping it would leave a real gap in retrieval.
        """
        covered = set()
        for span in spans:
            covered.update(range(span['start_line'], span['end_line'] + 1))

        gaps = []
        current = []
        for lineno in range(1, len(lines) + 1):
            if lineno in covered or not lines[lineno - 1].strip():
                if current:
                    gaps.append(current)
                    current = []
                continue
            current.append(lineno)
        if current:
            gaps.append(current)

        return [
            {
                'start_line': gap[0],
                'end_line': gap[-1],
                'symbol': '',
                'kind': 'module_level',
            }
            for gap in gaps
        ]

    def _build_chunk(self, span, lines, filename, language):
        body = '\n'.join(lines[span['start_line'] - 1:span['end_line']])
        return self._chunk_dict(
            body=body,
            filename=filename,
            language=language,
            symbol=span['symbol'],
            kind=span['kind'],
            start_line=span['start_line'],
            end_line=span['end_line'],
        )

    def _window_chunks(self, content, filename, language):
        """Overlapping line windows - the fallback for anything we cannot parse."""
        lines = content.splitlines()
        if not lines:
            return []

        step = max(WINDOW_LINES - WINDOW_OVERLAP_LINES, 1)
        chunks = []
        for start in range(0, len(lines), step):
            window = lines[start:start + WINDOW_LINES]
            if not any(line.strip() for line in window):
                continue
            chunks.append(self._chunk_dict(
                body='\n'.join(window),
                filename=filename,
                language=language,
                symbol='',
                kind='window',
                start_line=start + 1,
                end_line=min(start + WINDOW_LINES, len(lines)),
            ))
            if start + WINDOW_LINES >= len(lines):
                break
        return chunks

    def _chunk_dict(self, body, filename, language, symbol, kind, start_line, end_line):
        # The header is part of the embedded text on purpose: without it the vector
        # never sees the path or symbol name, which are exactly what people search for.
        location = f"{symbol} ({kind})" if symbol else kind
        header = f"# {filename} | {language or 'text'} | {location} | L{start_line}-{end_line}"
        return {
            'chunk': f"{header}\n{body}",
            'body': body,
            'filename': filename,
            'language': language or '',
            'symbol': symbol,
            'kind': kind,
            'start_line': start_line,
            'end_line': end_line,
        }
