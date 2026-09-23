"""`ast.parse` for Python source newer than the running interpreter (BACK-1394)."""

import ast
import io
import re
import tokenize
import warnings
from typing import List, Optional, Tuple

# PEP 750 template-string prefixes; a 3.13 tokenizer reads `t"..."` as NAME + STRING.
_T_PREFIX = re.compile(r'(?:[tT][rR]?|[rR][tT])')
_STRING_STARTS = {tokenize.STRING} | (
    {tokenize.FSTRING_START} if hasattr(tokenize, 'FSTRING_START') else set())
_OPEN, _CLOSE = ('(', '[', '{'), (')', ']', '}')

_Edit = Tuple[int, int, int, str]  # (row, col, chars replaced, replacement)


def parse_python(source: str, filename: str = '<unknown>') -> ast.Module:
    """`ast.parse`, but a file using Python 3.14 syntax still parses on an older
    interpreter instead of raising SyntaxError.

    reveal's stdlib-ast consumers (surface, calls ?uncalled, several rules) all
    skip a file that fails to parse, so on the 3.13 interpreter reveal ships
    with, one `except ValueError, TypeError:` (PEP 758) or `t"..."` (PEP 750)
    made the whole file silently disappear. On a SyntaxError the source is
    retried with those constructs rewritten to their pre-3.14 equivalents; line
    numbers are unchanged. The original error is raised if the retry fails too.

    SyntaxWarnings (e.g. invalid escape sequences) belong to the file being
    analyzed, not to reveal, and are not printed.
    """
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        try:
            return ast.parse(source, filename=filename)
        except SyntaxError as original:
            compat = downlevel_source(source)
            if compat is None:
                raise
            try:
                return ast.parse(compat, filename=filename)
            except SyntaxError:
                raise original from None


def downlevel_source(source: str) -> Optional[str]:
    """`source` with PEP 758 unparenthesized `except A, B:` parenthesized and
    PEP 750 t-strings read as f-strings (same interpolation grammar), or None
    when there is nothing to rewrite."""
    tokens: List[tokenize.TokenInfo] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            tokens.append(tok)
    except (tokenize.TokenError, SyntaxError):
        pass  # rewrite what tokenized; the reparse decides whether it was enough
    edits: List[_Edit] = []
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NAME:
            continue
        if tok.string == 'except':
            edits.extend(_parenthesize_except(tokens, i + 1))
        elif _T_PREFIX.fullmatch(tok.string) and i + 1 < len(tokens) \
                and tokens[i + 1].type in _STRING_STARTS and tokens[i + 1].start == tok.end:
            prefix = tok.string.replace('t', 'f').replace('T', 'F')
            edits.append((tok.start[0], tok.start[1], len(tok.string), prefix))
    if not edits:
        return None
    lines = source.splitlines(keepends=True)
    for row, col, width, text in sorted(edits, reverse=True):
        line = lines[row - 1]
        lines[row - 1] = line[:col] + text + line[col + width:]
    return ''.join(lines)


def _parenthesize_except(tokens: List[tokenize.TokenInfo], start: int) -> List[_Edit]:
    """Edits wrapping `except[*] A, B:` as `except[*] (A, B):`. PEP 758 only
    allows the bare form without `as`, so a clause with `as` is left alone."""
    if start < len(tokens) and tokens[start].string == '*':
        start += 1
    depth = 0
    has_comma = False
    for k in range(start, len(tokens)):
        tok = tokens[k]
        if tok.type == tokenize.NEWLINE:
            return []
        if tok.type == tokenize.NAME:
            if depth == 0 and tok.string == 'as':
                return []
            continue
        if tok.type != tokenize.OP:
            continue
        if tok.string in _OPEN:
            depth += 1
        elif tok.string in _CLOSE:
            depth -= 1
        elif depth == 0 and tok.string == ',':
            has_comma = True
        elif depth == 0 and tok.string == ':':
            if not has_comma or k == start:
                return []
            return [(tokens[start].start[0], tokens[start].start[1], 0, '('),
                    (tok.start[0], tok.start[1], 0, ')')]
    return []
