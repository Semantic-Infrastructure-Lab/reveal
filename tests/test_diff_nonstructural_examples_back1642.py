"""BACK-1642: diff:// examples must not promise schema/config drift it cannot report.

`diff://` compares code structure (functions, classes, imports; see
reveal/diff.py::compute_structure_diff). A resource whose structure has none of those --
sqlite://, env://, JSON/YAML files, and mysql:// by the same code path -- cannot be compared:
the compare step would call it equal, so the adapter declines it (BACK-1689, tests/
test_diff_not_applicable_back1689.py). The first group below pins both halves; the second pins
that no help text or guide still presents such a comparison as an example.

mysql:// itself needs a live server, so only its URI parsing and the shared compare step
are exercised here; nothing below claims MySQL output.
"""

import re
import sqlite3
from pathlib import Path

import pytest

from reveal.adapters.diff.adapter import DiffAdapter
from reveal.adapters.diff.help import get_schema
from reveal.adapters.diff.parsing import parse_diff_uris
from reveal.adapters.help_data import load_help_data
from reveal.diff import compute_structure_diff
from reveal.errors import NotApplicableError

pytestmark = pytest.mark.component

ROOT = Path(__file__).resolve().parent.parent
DIFF_GUIDE = ROOT / 'reveal' / 'docs' / 'adapters' / 'DIFF_ADAPTER_GUIDE.md'
RECIPES = ROOT / 'reveal' / 'docs' / 'guides' / 'RECIPES.md'
NON_STRUCTURAL = re.compile(r'diff://(mysql|sqlite|env)://')


def _summary_counts(structure_diff):
    return sum(sum(bucket.values()) for bucket in structure_diff['summary'].values())


def test_sqlite_databases_with_different_schemas_are_declined(tmp_path):
    left, right = tmp_path / 'a.db', tmp_path / 'b.db'
    with sqlite3.connect(left) as conn:
        conn.execute('create table t(id integer)')
    with sqlite3.connect(right) as conn:
        conn.execute('create table t(id integer, extra text)')
        conn.execute('create table u(x integer)')
    uri = f'sqlite://{left.as_posix()}:sqlite://{right.as_posix()}'
    with pytest.raises(NotApplicableError):
        DiffAdapter(uri).get_structure()


def test_json_files_with_different_content_are_declined(tmp_path):
    left, right = tmp_path / 'a.json', tmp_path / 'b.json'
    left.write_text('{"a": 1}\n', encoding='utf-8')
    right.write_text('{"a": 2, "b": 3}\n', encoding='utf-8')
    with pytest.raises(NotApplicableError):
        DiffAdapter(f'{left.as_posix()}:{right.as_posix()}').get_structure()


def test_mysql_server_shaped_structures_compare_equal_in_the_compare_step():
    """Keys are those MySQLAdapter.get_structure() returns; the compare step reads none of them."""
    prod = {'type': 'mysql_server', 'server': 'prod:3306', 'version': '8.0.35',
            'health_status': 'healthy', 'storage': {'databases': 3}}
    staging = {'type': 'mysql_server', 'server': 'staging:3306', 'version': '8.0.36',
               'health_status': 'warning', 'storage': {'databases': 7}}
    assert _summary_counts(compute_structure_diff(prod, staging)) == 0


def test_negative_control_code_structures_do_differ():
    left = {'functions': [{'name': 'a', 'line': 1, 'line_end': 2}], 'classes': [], 'imports': []}
    right = {'functions': [], 'classes': [], 'imports': []}
    assert _summary_counts(compute_structure_diff(left, right)) > 0


def test_mysql_uris_parse_so_the_syntax_is_not_the_problem():
    assert parse_diff_uris('mysql://prod/db:mysql://staging/db') == ('mysql://prod/db', 'mysql://staging/db')
    assert parse_diff_uris('mysql://u:p@h1:3306/db:mysql://u:p@h2:3306/db') == (
        'mysql://u:p@h1:3306/db', 'mysql://u:p@h2:3306/db')


def test_schema_examples_do_not_promise_non_structural_comparisons():
    uris = [example['uri'] for example in get_schema()['example_queries']]
    assert not [uri for uri in uris if NON_STRUCTURAL.match(uri)]


def test_help_yaml_examples_do_not_promise_non_structural_comparisons():
    uris = [example['uri'] for example in load_help_data('diff')['examples']]
    assert not [uri for uri in uris if NON_STRUCTURAL.match(uri)]


def test_schema_comparison_types_do_not_list_schema_drift():
    banned = ('drift', 'environment', 'configuration')
    assert not [t for t in get_schema()['comparison_types'] if any(word in t.lower() for word in banned)]


def test_adapter_docstring_does_not_promise_schema_drift():
    assert 'schema drift' not in (DiffAdapter.__doc__ or '').lower()


@pytest.mark.parametrize('path', [DIFF_GUIDE, RECIPES], ids=lambda p: p.name)
def test_guides_have_no_runnable_non_structural_diff_command(path):
    commands = [line.strip() for line in path.read_text(encoding='utf-8').splitlines()
                if line.strip().startswith('reveal ') and NON_STRUCTURAL.search(line)]
    assert not commands, commands


def test_diff_guide_states_the_limitation():
    text = DIFF_GUIDE.read_text(encoding='utf-8')
    assert 'not applicable' in text
    assert 'requires a live MySQL connection' in text
