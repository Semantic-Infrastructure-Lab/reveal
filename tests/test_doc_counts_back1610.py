"""BACK-1610: the MCP tool count the shipped docs state must match the server.

The docs typed it four ways (five, six, ten, 5) and only MCP_SETUP.md's copy
had a test. This scans every shipped doc for "N tools" / "N MCP tools" and
checks each against the registered tools, so a new copy is covered without a
new guard. (Adapter, language and rule counts are the V013/V012/V029 rules'
job; they run on reveal:// in CI.)

Release-history lines ("- **v0.64.0** - ... (5 tools)", ROADMAP's "- ✅ ...")
record what was true then and are skipped.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
_HISTORY_LINE = re.compile(r'^\s*- (\*\*v\d|✅)')
_WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7,
          'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12}
_TOOLS = re.compile(r'\b(\d+|' + '|'.join(_WORDS) + r') (?:MCP )?tools\b', re.IGNORECASE)


def _shipped_docs():
    yield ROOT / 'README.md'
    yield ROOT / 'ROADMAP.md'
    yield from sorted((ROOT / 'reveal' / 'docs').rglob('*.md'))
    yield ROOT / 'reveal' / 'mcp_server.py'


def _stated_tool_counts():
    hits = []
    for path in _shipped_docs():
        for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if _HISTORY_LINE.match(line):
                continue
            for m in _TOOLS.finditer(line):
                word = m.group(1).lower()
                hits.append((f'{path.relative_to(ROOT).as_posix()}:{n}', _WORDS.get(word) or int(word)))
    return hits


def test_stated_mcp_tool_counts_match_the_server():
    from reveal.mcp_server import mcp
    expected = len(mcp._tool_manager._tools)
    hits = _stated_tool_counts()
    assert hits, 'no doc states the MCP tool count: the pattern matches nothing (positive control)'
    wrong = [f'{where} says {n}' for where, n in hits if n != expected]
    assert not wrong, f'reveal-mcp registers {expected} tools, but: ' + '; '.join(wrong)


def test_retired_savings_range_is_not_restated():
    """BENCHMARKS.md retired the 10-150x headline (it compared unlike operations);
    the measured claim is typically 3.9-15x. Only BENCHMARKS.md may name it."""
    retired = re.compile(r'\b10\s*[-–]\s*150x')
    hits = [f'{path.relative_to(ROOT).as_posix()}:{n}'
            for path in _shipped_docs() if path.name != 'BENCHMARKS.md'
            for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1)
            if retired.search(line) and not _HISTORY_LINE.match(line)]
    assert not hits, 'the retired 10-150x range is restated at: ' + ', '.join(hits)
