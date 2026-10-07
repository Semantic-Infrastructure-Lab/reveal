"""Split file text into lines the way `grep -n`, `wc -l`, compilers and editors count them (BACK-1722).

A line ends at ``\\n`` (``\\r\\n`` too). ``str.splitlines()`` also ends one at form feed, vertical tab,
FS/GS/RS, NEL (U+0085) and U+2028/U+2029, so a GNU C file with a ``^L`` page break or a Python string
holding U+2028 got every later line number one too high -- against tree-sitter, ``grep -n`` and the
user's editor. Every site that holds file content and reports or compares a line number or count
splits with ``split_lines``; ``scripts/check_boundaries.py`` (rule ``splitlines``) keeps it that way.
"""

import re
from typing import List

_WITH_TERMINATOR = re.compile(r'[^\n]*\n|[^\n]+')


def split_lines(text: str, keepends: bool = False) -> List[str]:
    """Lines of ``text``, split at ``\\n`` only (a trailing ``\\r`` of a ``\\r\\n`` pair is dropped).

    Like ``str.splitlines()``, a final newline does not start an extra empty line and ``''`` has no
    lines. A lone ``\\r`` is not a line end here; ``FileAnalyzer._read_file`` reads in text mode,
    whose universal newlines already turned it into ``\\n``. ``keepends=True`` keeps every
    terminator (``\\r\\n`` included) so the pieces join back to ``text``.
    """
    if keepends:
        return _WITH_TERMINATOR.findall(text)
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    return [line[:-1] if line.endswith('\r') else line for line in lines]


def normalize_newlines(text: str) -> str:
    """``text`` with every ``\\r\\n`` and lone ``\\r`` turned into ``\\n``: what a text-mode read gives.

    An analyzer reads its file in text mode, whose universal newlines make a lone ``\\r`` a line
    break. Text decoded raw (a git blob, the binary-mode fallback in ``FileAnalyzer._read_file``)
    goes through this before it is split or sliced by the analyzer's line numbers, or a lone
    ``\\r`` shifts every later line by one (BACK-1736).
    """
    return text.replace('\r\n', '\n').replace('\r', '\n')
