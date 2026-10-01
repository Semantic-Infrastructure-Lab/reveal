"""BACK-1605: an unknown --select/--ignore rule code is an error, not a clean result.

A pattern that matches no rule filtered the rule set to nothing, so
`reveal <dir> --check --select ZZZ999` printed "No issues found" and exited 0, and
MCP reveal_check(select='S012') -- its own docstring example -- said the same.
"""
import re
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.rules import RuleRegistry, parse_rule_patterns

FILE = str(Path(__file__).resolve().parents[1] / 'reveal' / 'config.py')


class TestParseRulePatterns:
    @pytest.mark.parametrize('value, expected', [
        ('B', ['B']),                     # category prefix
        ('B0', ['B0']),                   # partial prefix
        ('C901', ['C901']),               # exact code
        (' B , S701 ,, ', ['B', 'S701']),  # spaces and empty items dropped
    ])
    def test_known_patterns_pass(self, value, expected):
        assert parse_rule_patterns(value) == expected

    def test_unknown_patterns_are_named(self):
        with pytest.raises(ValueError, match=r'unknown rule code or prefix: ZZZ999, Q1 \('):
            parse_rule_patterns('B,ZZZ999,S701,Q1')

    def test_disabled_rules_count_as_known(self):
        RuleRegistry.discover()
        disabled = [r['code'] for r in RuleRegistry.list_rules(include_disabled=True, include_internal=True)
                    if not r.get('enabled', True)]
        assert disabled, 'positive control: some rule is disabled by default'
        assert RuleRegistry.unknown_patterns(disabled) == []


# Every CLI form that declares --select/--ignore.
@pytest.mark.parametrize('argv', [
    [FILE, '--check', '--select', 'ZZZ999'],
    [FILE, '--check', '--ignore', 'ZZZ999'],
    ['check', FILE, '--select', 'ZZZ999'],
    ['check', FILE, '--ignore', 'ZZZ999'],
    ['review', FILE, '--select', 'ZZZ999'],
    ['health', FILE, '--select', 'ZZZ999'],
], ids=lambda a: ' '.join(a[:-1]).replace(FILE, 'FILE'))
def test_cli_unknown_code_is_a_usage_error(argv):
    result = _run_reveal_direct(*argv)
    assert result.returncode == 2
    assert 'unknown rule code or prefix: ZZZ999' in result.stderr
    assert 'No issues found' not in result.stdout


def test_cli_known_code_still_runs():
    result = _run_reveal_direct('check', FILE, '--select', 'C901')
    assert result.returncode in (0, 1), result.stderr
    assert 'unknown rule code' not in result.stderr


class TestMcpRevealCheck:
    def test_unknown_select_and_ignore_are_errors(self):
        from reveal.mcp_server import reveal_check
        assert reveal_check(FILE, select='S012') == (
            '[reveal error: unknown rule code or prefix: S012 (reveal --rules lists them)]')
        assert reveal_check(FILE, ignore='ZZ').startswith('[reveal error: unknown rule code')

    def test_docstring_examples_name_real_rules(self):
        from reveal.mcp_server import reveal_check
        doc = reveal_check.__doc__
        examples = re.findall(r"e\.g\. '([^']+)'(?: or '([^']+)')?", doc)
        values = [v for pair in examples for v in pair if v]
        assert 'B006,S701' in values, 'positive control: the select example is found'
        for value in values:
            parse_rule_patterns(value)
