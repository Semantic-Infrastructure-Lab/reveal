"""Function-body helpers shared by the duplicate-detection rules (D001, D002)."""

import re
from typing import Any, Dict


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

    lines = content.splitlines()
    if start > len(lines) or end > len(lines):
        return ""

    # start is 1-indexed, so lines[start:end] begins after the signature line.
    body_lines = lines[start:end]
    return '\n'.join(body_lines) if body_lines else ""


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
    statements = [line.strip() for line in body.splitlines()]
    statements = [line for line in statements if line and line not in _BLOCK_PUNCTUATION]
    return len(statements) == 1 and bool(_TRIVIAL_STATEMENT.match(statements[0]))
