"""Retirement lookup builds a parser only to resolve an actual prefix candidate."""
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


@pytest.mark.parametrize('option,expected,builds', [
    ('--exits', None, 0), ('--format', None, 0), ('--depth', None, 0),
    ('--returns', 'flag:--returns', 0),
    ('--flow', None, 1), ('--flowt', 'flag:--flowto', 1),
])
def test_only_prefix_candidates_need_parser_identity(monkeypatch, option, expected, builds):
    observed = _count_builds(monkeypatch)
    assert retired_flag_key(option) == expected
    assert len(observed) == builds


@pytest.mark.parametrize('flag,expected_builds,canonical', [
    ('--exits', 0, 'exits'), ('--returns', 0, 'exits'),
    ('--flow', 1, 'flow'), ('--flow=if', 1, 'flow'), ('--flowt', 1, 'exits'),
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
