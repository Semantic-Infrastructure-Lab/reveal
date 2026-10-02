"""BACK-1610: help text that restated a list the registry owns.

- check --help and --select listed 7 rule categories (B, C, I, M, R, S, T)
  while --rules lists 14. The legend now comes from rules/base.CATEGORY_TITLES;
  the table is checked against the registry in both directions.
- help://languages printed "()" for every explicit analyzer's extensions.
"""

import pytest

from reveal.rules import RuleRegistry
from reveal.rules.base import CATEGORY_TITLES, RulePrefix, category_legend


def _shipped_categories():
    return {r['category'] for r in RuleRegistry.list_rules(include_internal=False)}


def test_every_category_with_a_rule_has_a_title():
    assert _shipped_categories() <= set(CATEGORY_TITLES)


def test_every_titled_category_has_a_rule():
    assert set(CATEGORY_TITLES) <= _shipped_categories()


def test_titles_are_rule_prefixes():
    assert set(CATEGORY_TITLES) <= {p.value for p in RulePrefix}


def test_check_help_names_every_category():
    from reveal.cli.commands.check import create_check_parser
    text = ' '.join(create_check_parser().format_help().split())
    for prefix, title in CATEGORY_TITLES.items():
        assert f'{prefix}={title}' in text
    assert category_legend() in ' '.join(text.split())


def test_help_languages_lists_each_analyzers_extensions():
    from contextlib import redirect_stdout
    from io import StringIO
    from reveal.cli.languages import build_languages_payload
    from reveal.main import main
    out = StringIO()
    with redirect_stdout(out):
        main(['reveal', 'help://languages'])
    text = out.getvalue()
    assert '()' not in text
    for entry in build_languages_payload()['explicit']:
        assert f"({', '.join(entry['extensions'])})" in text, entry['name']


def test_mcp_check_doc_names_every_category():
    """BACK-1612: reveal_check's description called B/F/N/V 'style violations'
    and left the other series out; its series list must cover every category."""
    import re
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    doc = ' '.join((reveal_check.__doc__ or '').split())
    legend = doc.split('Rule series:', 1)[1].split('(full list', 1)[0]
    named = set(re.findall(r'(?:^|, )([A-Z]) ', legend.strip()))
    assert named == set(CATEGORY_TITLES), legend
