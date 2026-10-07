"""Split file text into lines the way `grep -n`, `wc -l`, compilers and editors count them (BACK-1722).

A line ends at ``\\n`` (``\\r\\n`` too). ``str.splitlines()`` also ends one at form feed, vertical tab,
FS/GS/RS, NEL (U+0085) and U+2028/U+2029, so a GNU C file with a ``^L`` page break or a Python string
holding U+2028 got every later line number one too high -- against tree-sitter, ``grep -n`` and the
user's editor. Every site that holds file content and reports or compares a line number or count
splits with ``split_lines``; ``scripts/check_boundaries.py`` (rule ``splitlines``) keeps it that way.
"""

from typing import List


def split_lines(text: str) -> List[str]:
    """Lines of ``text``, split at ``\\n`` only (a trailing ``\\r`` of a ``\\r\\n`` pair is dropped).

    Like ``str.splitlines()``, a final newline does not start an extra empty line and ``''`` has no
    lines. A lone ``\\r`` is not a line end here; ``FileAnalyzer._read_file`` reads in text mode,
    whose universal newlines already turned it into ``\\n``.
    """
    lines = text.split('\n')
    if lines[-1] == '':
        lines.pop()
    return [line[:-1] if line.endswith('\r') else line for line in lines]
