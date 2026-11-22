"""Element views print their standing caveats as one Rules pointer line (BACK-2627 S6, BACK-2599, COMMAND_MODEL rule 7).

A standing caveat is true of every answer of its view: the flow skeleton's scope sentence, the exits view's counting and
implicit-tail rules, the transitive boundary's assignment coverage, and the varflow trust note of a language that is not
fully conformance-verified. Text printed each sentence on every answer; it now prints one ``Rules: --format json (...)``
line naming the JSON fields that keep the full text, which stay as they were. What the request selected (the navigation
depth, the exit scope's mode) and request-specific warnings stay in the text.
"""

import json
import shutil
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run

FIXTURES = Path(__file__).parent / 'fixtures' / 'conformance'


@pytest.fixture(scope='module')
def files(tmp_path_factory):
    """Private copies: the transitive walk would otherwise scan the checkout (BACK-2159)."""
    out = {}
    for language, name in (('python', 'sample.py'), ('scala', 'sample.scala')):
        folder = tmp_path_factory.mktemp(language)
        shutil.copy(FIXTURES / language / name, folder / name)
        out[language] = (folder / name).as_posix()
    return out


def _text(*argv):
    result = run(*argv)
    assert result.returncode == 0, result.stderr
    return result


def _json(*argv):
    result = run(*argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _rules_lines(stdout):
    return [line for line in stdout.splitlines() if line.startswith('Rules: ')]


def test_flow_text_points_at_the_structure_scope(files):
    result = _text(files['python'], 'process_order', '--view', 'flow')
    assert _rules_lines(result.stdout) == [
        'Rules: --format json (meta.structure_scope.rule, meta.structure_scope.exit_sites)']
    assert 'Skeleton scope' not in result.stdout
    assert 'Recognized structural nodes' not in result.stdout
    assert result.stdout.startswith('Navigation depth 3\n')  # what the request selected stays


def test_flow_json_keeps_the_structure_scope(files):
    scope = _json(files['python'], 'process_order', '--view', 'flow')['meta']['structure_scope']
    assert scope['rule'] == 'Recognized structural nodes; exit expressions may be omitted.'
    assert scope['exit_sites'].startswith('Inspect ')


def test_exits_text_points_at_the_exit_scope(files):
    result = _text(files['python'], 'process_order', '--view', 'exits')
    assert _rules_lines(result.stdout) == [
        'Rules: --format json (meta.exit_scope.rule, meta.exit_scope.implicit_tail_rule)']
    assert 'Implicit tail returns' not in result.stdout
    assert result.stdout.startswith('Exit scope: selected callable execution regions\n')  # the mode stays


def test_exits_json_keeps_the_exit_scope(files):
    scope = _json(files['python'], 'process_order', '--view', 'exits')['meta']['exit_scope']
    assert scope['implicit_tail_rule'].startswith('Implicit tail returns are inferred only')
    assert scope['rule'].startswith('Candidate execution-region sites')


def test_transitive_boundary_text_points_at_the_warnings(files):
    result = _text(files['python'], 'process_order', '--view', 'boundary', '--transitive')
    assert _rules_lines(result.stdout) == ['Rules: --format json (meta.warnings)']
    assert 'Assignment coverage' not in result.stdout
    assert 'EFFECTS (--transitive, depth=2):' in result.stdout


def test_transitive_boundary_json_keeps_the_assignment_coverage(files):
    answer = _json(files['python'], 'process_order', '--view', 'boundary', '--transitive')
    assert any(w['message'].startswith('Assignment coverage:') for w in answer['meta']['warnings'])


def test_varflow_trust_note_is_the_pointer_on_a_smoke_tested_language(files):
    result = _text(files['scala'], 'processOrder', '--varflow', 'order')
    assert _rules_lines(result.stdout) == ['Rules: --format json (meta.warnings)']
    assert '--varflow is' not in result.stdout + result.stderr
    answer = _json(files['scala'], 'processOrder', '--varflow', 'order')
    assert any("--varflow is 'smoke-tested' for scala" in w['message'] for w in answer['meta']['warnings'])


@pytest.mark.parametrize('argv', [
    ('--view', 'boundary'),
    ('--view', 'effects'),
    ('--varflow', 'order'),
    ('--inputs',),
], ids=['boundary', 'effects', 'varflow-verified', 'inputs'])
def test_views_without_a_standing_caveat_print_no_rules_line(files, argv):
    # Negative control: no standing caveat, no pointer.
    assert _rules_lines(_text(files['python'], 'process_order', *argv).stdout) == []
