"""D001: Detect duplicate functions via normalized AST hashing.

Abusively lean approach:
- Normalize function body (strip whitespace, comments)
- Skip no-op hook bodies (a lone ``return []``/``return None``/``pass``): base
  implementations of extension points are identical by design (BACK-1049)
- Hash normalized content
- O(n) time, O(n) space where n = number of functions
- Zero new dependencies (stdlib only)

Performance:
- Single file: ~1-5ms for typical files
- Cross-file: Deferred (needs caching strategy)
"""

import io
import logging
import tokenize
from typing import List, Dict, Any, Optional
from hashlib import sha256
import re

from ..base import BaseRule, Detection, RulePrefix, Severity, RuleScope
from ._bodies import extract_function_body, is_trivial_hook_body
from reveal.utils.lines import split_lines

logger = logging.getLogger(__name__)


class D001(BaseRule):
    """Detect exact duplicate functions (normalized)."""

    code = "D001"
    scope = RuleScope.FILE
    message = "Duplicate function detected"
    category = RulePrefix.D
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Works on any language with functions
    version = "1.0.0"

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Find duplicate functions within a single file.

        Args:
            file_path: Path to file
            structure: Parsed structure from reveal analyzer
            content: File content

        Returns:
            List of detections for duplicates
        """
        if not structure or 'functions' not in structure:
            return []
        functions = structure['functions']
        if len(functions) < 2:
            return []
        classes = structure.get('classes', [])
        from reveal.registry import get_analyzer
        analyzer = get_analyzer(file_path, allow_fallback=False)
        python = getattr(analyzer, 'language', None) == 'python'
        scope_hashes = self._build_scope_hashes(functions, classes, content, python=python)
        return self._emit_duplicates(scope_hashes, file_path)

    def _build_scope_hashes(
        self, functions: list, classes: list, content: str, *, python: bool = False
    ) -> Dict[str, Dict[str, list]]:
        """Hash each function body grouped by containing class scope."""
        from collections import defaultdict

        def class_for(line: int) -> Optional[str]:
            for cls in classes:
                if cls.get('line', 0) <= line <= cls.get('line_end', 0):
                    return str(cls.get('name')) if cls.get('name') is not None else None
            return None

        scope_hashes: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for func in functions:
            func_body = extract_function_body(func, content)
            if not func_body or len(func_body.strip()) < 10:
                continue
            normalized = _normalize_python(func_body) if python else self._normalize(func_body)
            if not normalized or is_trivial_hook_body(normalized):
                continue
            func_hash = sha256(normalized.encode('utf-8')).hexdigest()[:16]
            scope = class_for(func.get('line', 0)) or '__module__'
            scope_hashes[scope][func_hash].append((
                func.get('name', '<unknown>'), func.get('line', 0), len(func_body)
            ))
        return scope_hashes

    def _emit_duplicates(
        self, scope_hashes: Dict[str, Dict[str, list]], file_path: str
    ) -> List[Detection]:
        """Report duplicate functions found within each scope."""
        detections: List[Detection] = []
        for _scope, hash_to_funcs in scope_hashes.items():
            for func_hash, instances in hash_to_funcs.items():
                if len(instances) < 2:
                    continue
                instances.sort(key=lambda x: x[1])
                original = instances[0]
                for duplicate in instances[1:]:
                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=duplicate[1],
                        message=f"{self.message}: '{duplicate[0]}' identical to '{original[0]}' (line {original[1]})",
                        suggestion=f"Refactor to share implementation with {original[0]}",
                        context=f"{duplicate[2]} chars, hash {func_hash}"
                    ))
        return detections

    def _normalize(self, code: str) -> str:
        """
        Normalize code to detect semantic duplicates.

        Removes:
        - Comments (all common styles)
        - Docstrings (Python triple quotes)
        - Whitespace variations
        - Empty lines

        Preserves:
        - Control flow structure
        - Operators
        - Identifiers (for now - stricter normalization can rename vars)
        - Literals

        Args:
            code: Raw function body

        Returns:
            Normalized code string
        """
        # Remove single-line comments
        # Python, Ruby, Shell: # comment
        code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        # C, JS, Rust, Go: // comment
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)

        # Remove multi-line comments
        # C, JS: /* comment */
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

        # Remove docstrings (Python)
        # Only remove standalone docstrings (at start of line), not string literals
        # in return statements, assignments, etc.
        code = re.sub(r'^\s*""".*?"""', '', code, flags=re.DOTALL | re.MULTILINE)
        code = re.sub(r"^\s*'''.*?'''", '', code, flags=re.DOTALL | re.MULTILINE)

        # Normalize whitespace
        # Collapse multiple spaces to single space
        code = re.sub(r'[ \t]+', ' ', code)
        # Remove empty lines
        code = re.sub(r'\n\s*\n', '\n', code)
        # Strip leading/trailing whitespace per line
        lines = [line.strip() for line in split_lines(code)]
        code = '\n'.join(lines)

        return code.strip()


def _python_tokens(code: str) -> Optional[List[tokenize.TokenInfo]]:
    """Keep interpolated strings opaque on both old and new tokenizer APIs."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, SyntaxError):
        return None
    if any(token.type == tokenize.ERRORTOKEN for token in tokens):
        return None
    result = []
    depth = 0
    first = None
    for token in tokens:
        name = tokenize.tok_name[token.type]
        if name in ('FSTRING_START', 'TSTRING_START'):
            if not depth:
                first = token
            depth += 1
        elif name in ('FSTRING_END', 'TSTRING_END'):
            depth -= 1
            if not depth and first is not None:
                text = _source_span(code, first.start, token.end)
                result.append(tokenize.TokenInfo(tokenize.STRING, text, first.start, token.end, first.line))
        elif not depth:
            result.append(token)
    return result if depth == 0 else None


def _source_span(code: str, start: tuple, end: tuple) -> str:
    lines = split_lines(code)
    if start[0] == end[0]:
        return lines[start[0] - 1][start[1]:end[1]]
    return '\n'.join([lines[start[0] - 1][start[1]:],
                       *lines[start[0]:end[0] - 1], lines[end[0] - 1][:end[1]]])


def _is_docstring(tokens: List[tokenize.TokenInfo]) -> bool:
    """A plain string expression, including parentheses/implicit concatenation."""
    strings = [token for token in tokens if token.type == tokenize.STRING]
    return bool(strings) and all(
        (token.type == tokenize.STRING and token.string.lstrip('rRuU').startswith(('"', "'")))
        or token.string in ('(', ')', ';') for token in tokens)


def _docstring_spans(tokens: List[tokenize.TokenInfo]) -> list:
    """Only a function/class suite's first statement can supply its docstring.

    The input is an extracted function body. Control-flow suites do not acquire
    docstrings; later standalone strings and assigned/returned strings are code.
    Inline nested suites are retained conservatively.
    """
    spans = []
    suites = [True]
    next_suite = True  # initial indentation belongs to the extracted function
    statement: List[tokenize.TokenInfo] = []
    for token in tokens:
        if token.type == tokenize.INDENT:
            suites.append(next_suite)
            next_suite = False
        elif token.type == tokenize.DEDENT:
            if len(suites) > 1:
                suites.pop()
        elif token.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
            if statement:
                first = _first_statement(statement)
                if suites[-1] and _is_docstring(first):
                    spans.append((first[0].start, first[-1].end))
                suites[-1] = False
                names = [item.string for item in statement[:2]]
                next_suite = (names[:1] in (['def'], ['class']) or names == ['async', 'def'])
                statement = []
        elif token.type not in (tokenize.COMMENT, tokenize.NL, tokenize.ENCODING):
            statement.append(token)
    return spans


def _first_statement(tokens: List[tokenize.TokenInfo]) -> List[tokenize.TokenInfo]:
    for index, token in enumerate(tokens):
        if token.string == ';':
            return tokens[:index + 1]
    return tokens


def _normalize_python(code: str) -> str:
    """Normalize Python trivia without rewriting any literal's source bytes."""
    tokens = _python_tokens(code)
    if tokens is None:
        return code  # unknown lexical source never goes through destructive regexes
    docs = _docstring_spans(tokens)
    offsets = [0]
    for line in split_lines(code):
        offsets.append(offsets[-1] + len(line) + 1)
    def offset(position):
        return offsets[position[0] - 1] + position[1]
    edits = [(offset(start), offset(end), '') for start, end in docs]
    prefix = '__D001_LITERAL_'
    while prefix in code:
        prefix += '_'
    literals = {}
    for token in tokens:
        if any(start <= token.start and token.end <= end for start, end in docs):
            continue
        if token.type == tokenize.COMMENT:
            edits.append((offset(token.start), offset(token.end), ''))
        elif token.type == tokenize.STRING:
            marker = f'{prefix}{len(literals)}__'
            literals[marker] = token.string
            edits.append((offset(token.start), offset(token.end), marker))
    for start, end, replacement in sorted(edits, reverse=True):
        code = code[:start] + replacement + code[end:]
    code = re.sub(r'[ \t]+', ' ', code)
    code = re.sub(r'\n\s*\n', '\n', code)
    code = '\n'.join(line.strip() for line in split_lines(code)).strip()
    for marker, literal in literals.items():
        code = code.replace(marker, literal)
    return code
