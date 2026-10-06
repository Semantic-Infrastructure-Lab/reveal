"""AGENT_HELP.md points at help://quick for routing and keeps no second table (BACK-1055 slice 3).

help://quick is the intent -> tool router. The hand-written Decision Tree that used to sit in
AGENT_HELP.md duplicated it and drifted (it sent cross-file text search to ast://?name=). The
section now only points at help://quick; these tests keep it that way.
"""
import re
from pathlib import Path

from reveal.adapters.help import HelpAdapter

AGENT_HELP = Path(__file__).resolve().parent.parent / 'reveal' / 'docs' / 'AGENT_HELP.md'
_ARROW = re.compile(r'^\s*(?:[├└]─|→)', re.MULTILINE)


def _section(markdown):
    return markdown.split('\n## Decision Tree\n', 1)[1].split('\n## ', 1)[0]


def _has_second_table(section):
    return '```' in section or bool(_ARROW.search(section)) or '→' in section


def test_decision_tree_section_points_at_help_quick():
    section = _section(AGENT_HELP.read_text(encoding='utf-8'))
    assert 'reveal help://quick' in section
    assert not _has_second_table(section)


def test_second_table_check_bites():
    """Negative control: the old tree shape is reported."""
    old = "Need to inspect code?\n```\n├─ Unknown file? → reveal file.py\n```\n"
    assert _has_second_table(old)


def test_help_quick_routes_the_old_tree_intents():
    """Intents the removed tree carried live in help://quick now (e.g. --check, --grep)."""
    quick = HelpAdapter('').get_element('quick')
    uses = {e['use'] for e in quick['decision_tree']}
    assert {'--check', '--grep', 'ast://', 'reveal FILE NAME'} <= uses
