"""AGENT_HELP.md's Decision Tree routes only to tools help://quick routes to (BACK-1055 slice 3).

help://quick's curated intents and QUICK_RANK commands are the intent router; the
Decision Tree in AGENT_HELP.md is a hand-written subset of it. Its commands sit in a
plain (not bash) fence, so the recipe harness never runs them, and nothing checked that
the tree and help://quick name the same tools. This gate compares the tool vocabulary:
every URI scheme and --flag the tree names must be one help://quick also names.

It checks tools, not which intent maps to which tool: a line sending an intent to a
different tool that help://quick also knows is not caught (the 'Across multiple files'
text-search line sent to ast://?name= instead of --grep was fixed by hand in this slice).
"""
import re
from pathlib import Path

from reveal.adapters.help import HelpAdapter

AGENT_HELP = Path(__file__).resolve().parent.parent / 'reveal' / 'docs' / 'AGENT_HELP.md'
_TOOL = re.compile(r'([a-z][a-z0-9_-]*)://|(?<![\w-])(--[a-z][a-z0-9-]*)')


def _tools(text):
    return {scheme + '://' if scheme else flag for scheme, flag in _TOOL.findall(text)}


def _tree_commands(markdown):
    """The command side ('→ ...') of every Decision Tree line."""
    section = markdown.split('\n## Decision Tree\n', 1)[1].split('\n## ', 1)[0]
    block = section.split('```', 2)[1]
    return [line.split('→', 1)[1] for line in block.splitlines() if '→' in line]


def _quick_tools(quick):
    texts = [c['cmd'] for c in quick['commands']]
    texts += [f"{e['use']} {e['example']}" for e in quick['decision_tree']]
    return _tools(' '.join(texts))


def _unrouted(markdown, quick):
    return sorted(_tools(' '.join(_tree_commands(markdown))) - _quick_tools(quick))


def test_decision_tree_tools_are_routed_by_help_quick():
    quick = HelpAdapter('').get_element('quick')
    markdown = AGENT_HELP.read_text(encoding='utf-8')
    assert len(_tree_commands(markdown)) >= 10
    assert _unrouted(markdown, quick) == []


def test_decision_tree_gate_bites():
    """Negative control: a tool help://quick does not route, and a dropped route, are reported."""
    quick = HelpAdapter('').get_element('quick')
    markdown = AGENT_HELP.read_text(encoding='utf-8')
    drifted = markdown.replace("→ reveal path/ --grep 'pattern'", "→ reveal 'zebra://path?q=pattern'")
    assert _unrouted(drifted, quick) == ['zebra://']
    no_grep = {**quick, 'decision_tree': [e for e in quick['decision_tree']
                                          if '--grep' not in f"{e['use']} {e['example']}"]}
    assert '--grep' in _unrouted(markdown, no_grep)
