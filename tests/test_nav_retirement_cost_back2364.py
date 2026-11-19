"""Retirement lookup is an exact key lookup: it builds no parser (BACK-2705; it once built one to resolve a prefix)."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.cli import parser
from reveal.cli.defaults import _option_names, _parser_defaults
from reveal.cli.invocation import retired_flag_key

pytestmark = pytest.mark.component


def _count_builds(monkeypatch):
    builds = []
    original = parser.create_argument_parser

    def counted(*args, **kwargs):
        builds.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(parser, 'create_argument_parser', counted)
    return builds


@pytest.mark.parametrize('option,expected', [
    ('--exits', None), ('--format', None), ('--depth', None), ('--returns', 'flag:--returns'),
    ('--flow', None),    # a live option that is a prefix of the retired --flowto is not it
    ('--flowt', None),   # nor is a prefix of a retired flag: it is an unknown option to the parser
])
def test_retired_flag_lookup_is_exact_and_builds_no_parser(monkeypatch, option, expected):
    observed = _count_builds(monkeypatch)
    assert retired_flag_key(option) == expected
    assert not observed


@pytest.mark.parametrize('flag,expected_builds,canonical', [
    ('--exits', 0, 'exits'), ('--returns', 0, 'exits'),
    ('--flow', 0, 'flow'), ('--flow=if', 0, 'flow'),  # --flowt is an unknown option since BACK-2705
])
def test_actual_navigation_avoids_unrelated_option_parser_rebuilds(
        tmp_path, monkeypatch, flag, expected_builds, canonical):
    path = tmp_path / 'example.py'
    path.write_text('def work(a):\n if a:\n  return 1\n return 2\n', encoding='utf-8')
    # Existing parser-default/name caches are outside retirement lookup's work.
    _parser_defaults()
    _option_names()
    observed = _count_builds(monkeypatch)
    result = _run_reveal_direct(path, 'work', flag, '--format', 'json', '--depth', '3')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer['meta']['flag'] == canonical
    if canonical == 'exits':
        assert answer['findings'] == [
            {'kind': 'RETURN', 'line': 3, 'text': 'return 1', 'gates': [{'line': 2, 'text': 'a'}]},
            {'kind': 'RETURN', 'line': 4, 'text': 'return 2', 'gates': []},
        ]
    else:
        expected = [('IF', 2)] if flag == '--flow=if' else [('IF', 2), ('RETURN', 3), ('RETURN', 4)]
        assert [(row['keyword'], row['line_start']) for row in answer['findings']] == expected
    assert len(observed) == expected_builds
