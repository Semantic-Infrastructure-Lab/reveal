"""Function-body helpers shared by the duplicate-detection rules (D001, D002)."""

import re
from typing import Any, Dict, List, Optional
from reveal.utils.lines import split_lines


def extract_function_body(func: Dict[str, Any], content: str) -> str:
    """Extract a function body from ``content`` using the structure's line numbers.

    Skips the definition line (def/func/function) so duplicates are found even
    when parameter names differ. ``line_end`` is the structure's field name.

    Returns:
        The body without its signature line, or "" when the range is unusable.
    """
    start = func.get('line', 0)
    end = func.get('line_end', start)

    if start == 0 or end == 0:
        return ""

    lines = split_lines(content)
    if start > len(lines) or end > len(lines):
        return ""

    definition = _signature_end(lines, start - 1, end)
    if definition is None:
        definition = _definition_line(lines, start - 1, end)
    body_lines = lines[definition + 1:end]
    return '\n'.join(body_lines) if body_lines else ""


_STRING_LITERAL = re.compile(r"""'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*\"""")
_LINE_COMMENT = re.compile(r'\s*(?:#|//).*$')


def _signature_end(lines: List[str], first: int, last: int) -> Optional[int]:
    """Index of the line that closes the signature, or None when none is found.

    Structure records start at the first decorator/annotation line (Python
    ``@task(...)``, Java ``@Override``), so the signature can sit several lines
    below. The signature closes on the first line, counting from ``first``, that
    ends outside every ``(``/``[`` with ``:`` (Python) or ``{`` (brace languages).
    One rule, no per-language branches (BACK-1837).
    """
    depth = 0
    for index in range(first, min(last, len(lines))):
        code = _LINE_COMMENT.sub('', _STRING_LITERAL.sub('""', lines[index])).rstrip()
        depth += sum(code.count(c) for c in '([') - sum(code.count(c) for c in ')]')
        if depth <= 0 and code.endswith((':', '{')):
            return index
    return None


def _definition_line(lines: List[str], first: int, last: int) -> int:
    """Fallback when no ``:``/``{`` terminator closes the signature (one-line
    ``def f(): ...``, Ruby ``def``): the Python ``def`` after any decorators, else ``first``."""
    if lines[first].lstrip().startswith('@'):
        for index in range(first + 1, last):
            if re.match(r'^\s*(?:async\s+)?def\s+', lines[index]):
                return index
    return first


# One statement that does nothing but hand back (or be) an empty value. Case-insensitive
# literals cover the None/null/nil/undefined, empty-collection, zero and boolean spellings
# of Python, JS/TS, Go, Ruby, Java and PHP.
_TRIVIAL_STATEMENT = re.compile(
    r"""^(?:pass|\.\.\.|return(?:\s+(?:none|null|nil|undefined|true|false|0|0\.0|""|''|\[\]|\{\}|\(\)))?)\s*;?$""",
    re.IGNORECASE,
)
_BLOCK_PUNCTUATION = frozenset({'{', '}', '};', 'end'})


def is_trivial_hook_body(body: str) -> bool:
    """True when ``body`` is a single no-op statement: ``pass``, a bare ``return`` or a
    ``return`` of None/null/empty collection/zero/boolean (BACK-1049).

    Such bodies are the base implementation of an extension-point hook: every hook
    is identical by design and each is its own override point, so equal (or merely
    similar) bodies say nothing about copy-paste. Pass the body in any form: a
    docstring or comments around the statement are ignored by normalizing first, and
    lone block punctuation (``{``, ``}``, ``end``) is skipped.
    """
    statements = [line.strip() for line in split_lines(body)]
    statements = [line for line in statements if line and line not in _BLOCK_PUNCTUATION]
    return len(statements) == 1 and bool(_TRIVIAL_STATEMENT.match(statements[0]))
