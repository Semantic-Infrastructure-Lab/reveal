"""The few nginx configuration grammar rules reveal's two nginx readers must share.

``analyzers/nginx.py`` reads a config line by line and ``adapters/nginx/adapter.py`` reads
it with regexes over the whole text. Each had its own idea of what a comment, a quoted
string and a block are, so a commented-out ``# server {`` became a server in one, a
``"}"`` inside a quoted value closed a block early in the other, and the two disagreed on
which locations exist (BACK-1725). They now route through the functions here.

The grammar: ``#`` starts a comment unless inside a quoted string; a string is quoted with
``'`` or ``"`` and ``\\`` escapes the next character; a directive ends at ``;`` and a block
opens at ``{`` and closes at the matching ``}``; braces and ``;`` inside a quoted string are
text. (An unquoted ``{`` in a regex location is not valid nginx; the config must quote it.)
"""
from typing import Iterator, List, Optional, Tuple


CODE, QUOTE, COMMENT = 'code', 'quote', 'comment'


def _scan(text: str) -> Iterator[Tuple[int, str, str]]:
    """Yield ``(index, char, state)`` for every character: ``CODE``, ``QUOTE`` (a quoted
    string, quotes included) or ``COMMENT`` (a ``#`` through the end of the line)."""
    quote = ''
    in_comment = False
    escaped = False
    for i, ch in enumerate(text):
        if in_comment:
            if ch == '\n':
                in_comment = False
                yield i, ch, CODE
            else:
                yield i, ch, COMMENT
        elif quote:
            yield i, ch, QUOTE
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quote:
                quote = ''
        elif ch in '\'"':
            quote = ch
            yield i, ch, QUOTE
        elif ch == '#':
            in_comment = True
            yield i, ch, COMMENT
        else:
            yield i, ch, CODE


def strip_comments(text: str) -> str:
    """*text* without comments, newlines kept so line numbers do not move. A ``#`` inside a
    quoted string stays."""
    return ''.join(ch for _, ch, state in _scan(text) if state != COMMENT)


def brace_delta(line: str) -> int:
    """Opening minus closing braces on *line*, ignoring comments and quoted strings."""
    return sum((ch == '{') - (ch == '}') for _, ch, state in _scan(line) if state == CODE)


def block_header(line: str, name: str) -> Optional[str]:
    """The arguments of a ``name ... {`` block opened on *line* (text between the keyword
    and the first unquoted ``{``), or None when *line* does not open one."""
    code = strip_comments(line).strip()
    if not code.startswith(name) or code[len(name):len(name) + 1] not in (' ', '\t', '{'):
        return None
    for i, ch, state in _scan(code):
        if ch == '{' and state == CODE:
            return code[len(name):i].strip()
    return None


def find_blocks(text: str, name: str) -> List[Tuple[str, str]]:
    """``(header, body)`` of every outermost ``name ... { ... }`` block in *text*, comments
    ignored. Blocks nested in another ``name`` block are part of that block's body; a
    ``name`` block inside a different block (a ``location`` in a ``server``) is found."""
    code = strip_comments(text)
    found: List[Tuple[str, str]] = []
    depth = 0
    stmt_start = 0       # start of the current statement at the current depth
    open_stack: List[Tuple[int, str, int]] = []  # (body_start, header, depth) of name blocks
    for i, ch, state in _scan(code):
        if state != CODE:
            continue
        if ch == ';':
            stmt_start = i + 1
        elif ch == '{':
            header_text = code[stmt_start:i].strip()
            words = header_text.split(None, 1)
            if not open_stack and words and words[0] == name:
                open_stack.append((i + 1, words[1].strip() if len(words) > 1 else '', depth))
            depth += 1
            stmt_start = i + 1
        elif ch == '}':
            depth -= 1
            if open_stack and open_stack[-1][2] == depth:
                body_start, header, _ = open_stack.pop()
                found.append((header, code[body_start:i]))
            stmt_start = i + 1
    return found
