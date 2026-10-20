"""calls gains ?callers=, a callee walk at depth, --detail, a stated walk rule and its declines
(BACK-2066 slice C2; BACK-2102).

- ``?callers=NAME`` is the callers mode; ``?target=`` is the same mode under its older name and
  answers identically. ``callers=FILE:NAME`` and ``callers&detail`` are rejected (exit 2): the
  callers index has no file filter and no per-caller detail.
- ``?callees=NAME|FILE:NAME&depth=N``: depth 1 keeps the per-definition call lists; depth 2-5 walks
  level by level (``walk_callees``) under the same ``calls_callees`` type, with a ``walk_rule``
  in JSON and a ``Rule:`` line in text. ``detail`` adds params and effects.
- W-CALLS-9 declines callee walks beyond depth 1 and ``detail`` (no oracle scores them);
  a language with no recall snapshot gets ``confidence: null`` and is named (W-CALLS-10).
- A complete answer for a name with no definition exits 2; lost evidence exits 3.
- Callees text shows ``scope_hidden`` (it printed only required-loss warnings).
- ``path:name`` shorthand with an explicit mode exits 2 (it silently answered the mode, BACK-2102).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run

APP = '''\
import os
from pkg.util import fmt


def helper(x, y=1):
    return open(x)


def main(key):
    helper(key)
    run(key)


def run(key):
    helper(os.getenv(key))
    fmt(key)


def lonely():
    return 1
'''

UTIL = '''\
import requests


def fmt(x):
    leaf()
    return requests.get(str(x))


def leaf():
    return 0
'''

ELIXIR = '''\
defmodule M do
  def run(x) do
    helper(x)
  end

  def helper(y), do: y
end
'''

HINT = 'entries hidden by .gitignore (use --no-gitignore to show)'
NOT_MEASURED = 'not measured in any language'


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'app.py').write_text(APP, encoding='utf-8')
    (root / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (root / 'pkg' / 'util.py').write_text(UTIL, encoding='utf-8')
    return root


def jrun(*args):
    result = run(*args, '--format', 'json', '--no-gitignore')
    return result, json.loads(result.stdout) if result.stdout.strip() else None


def warning_codes(answer):
    return [w.get('code') for w in answer['meta']['warnings']]


def edge_set(levels):
    return [(level['level'], edge['caller'], edge['callee'], edge['resolved'], edge.get('expanded'))
            for level in levels for edge in level['callees']]


# --- callers: the new name for target -------------------------------------------------------

@pytest.mark.parametrize('extra', ['', '&depth=2'])
def test_callers_answers_exactly_like_target(project, extra):
    new, new_json = jrun(f'calls://proj?callers=helper{extra}')
    old, old_json = jrun(f'calls://proj?target=helper{extra}')
    assert new.returncode == old.returncode == 0, (new.stderr, old.stderr)
    assert new_json == old_json
    assert new_json['type'] == 'calls_query' and new_json['total_callers'] == 2
    assert new.stderr == old.stderr


def test_callers_subcommand_flag_equals_the_uri(project):
    cli, cli_json = jrun('calls', 'proj', '--callers', 'helper', '--provenance')
    uri, uri_json = jrun('calls://proj?callers=helper', '--provenance')
    assert cli.returncode == uri.returncode == 0, (cli.stderr, uri.stderr)
    assert cli_json['execution'].pop('command').startswith('reveal calls proj --callers helper')
    assert uri_json['execution'].pop('command').startswith('reveal calls://proj?callers=helper')
    assert cli_json == uri_json


@pytest.mark.parametrize('query', ['callers=helper&target=helper', 'callers=helper&callees=main'])
def test_callers_is_one_mode_selector(project, query):
    result, answer = jrun(f'calls://proj?{query}')
    assert result.returncode == 2, result.stderr
    assert 'one mode per request' in answer['error'] and 'callers' in answer['error']


@pytest.mark.parametrize('query', ['callers=app.py:helper', 'target=app.py:helper'])
def test_callers_rejects_a_file_selector(project, query):
    result, answer = jrun(f'calls://proj?{query}')
    assert result.returncode == 2, result.stderr
    assert 'FILE:NAME' in answer['error']


@pytest.mark.parametrize('query', ['callers=helper&detail', 'target=helper&detail=true', 'rank=callers&detail'])
def test_detail_outside_callees_is_rejected(project, query):
    result, answer = jrun(f'calls://proj?{query}')
    assert result.returncode == 2, result.stderr
    assert 'detail applies to callees only' in answer['error']


def test_callers_detail_subcommand_is_rejected(project):
    result = run('calls', 'proj', '--callers', 'helper', '--detail')
    assert result.returncode == 2, result.stderr
    assert 'detail applies to callees only' in result.stderr


# --- callees at depth -----------------------------------------------------------------------

def test_callees_depth_two_lists_the_walkers_edges(project):
    from reveal.adapters.calls.index import callee_levels, walk_callees
    result, answer = jrun('calls://proj?callees=main&depth=2')
    assert result.returncode == 0, result.stderr
    assert answer['type'] == 'calls_callees'
    assert answer['depth'] == 2
    walk = callee_levels(walk_callees(str(project), 'main', depth=2))
    assert edge_set(answer['levels']) == edge_set(walk['levels'])
    assert edge_set(answer['levels']) == [
        (1, 'main', 'helper', True, True), (1, 'main', 'run', True, True),
        (2, 'run', 'helper', True, False), (2, 'run', 'os.getenv', False, False), (2, 'run', 'fmt', True, False)]
    for key in ('total_edges', 'total_resolved', 'total_unresolved', 'total_ambiguous'):
        assert answer[key] == walk[key], key
    assert (answer['total_edges'], answer['total_resolved'], answer['total_unresolved']) == (5, 4, 1)
    names = [(d['name'], d['level']) for d in answer['definitions']]
    assert names == [('main', 0), ('helper', 1), ('run', 1), ('fmt', 2)]
    # The per-definition call lists stay: the depth-1 view of the same answer.
    assert [(m['function'], m['calls']) for m in answer['matches']] == [('main', ['helper', 'run'])]
    assert answer['total_calls'] == 2
    assert 'applies to ?target and ?root only' not in result.stderr


def test_callees_depth_one_keeps_the_per_definition_answer(project):
    result, answer = jrun('calls://proj?callees=main')
    assert result.returncode == 0, result.stderr
    assert set(answer) == {'contract_version', 'type', 'source', 'source_type', 'meta', 'target', 'query',
                           'matches', 'total_calls', '_builtins_hidden', 'path'}
    explicit, explicit_answer = jrun('calls://proj?callees=main&depth=1')
    assert explicit.returncode == 0 and explicit_answer == answer


def test_callees_builtins_toggle_reaches_the_walk(project):
    hidden = jrun('calls://proj?callees=main&depth=2')[1]
    shown = jrun('calls://proj?callees=main&depth=2&builtins=true')[1]
    assert ('helper', 'open') not in {(e['caller'], e['callee']) for lvl in hidden['levels'] for e in lvl['callees']}
    assert ('helper', 'open') in {(e['caller'], e['callee']) for lvl in shown['levels'] for e in lvl['callees']}
    assert shown['walk_rule']['builtins'] == 'included' and hidden['walk_rule']['builtins'] == 'hidden'


def test_callees_file_selector_picks_one_files_definitions(project):
    (project / 'other.py').write_text('def fmt(v):\n    return v.upper()\n', encoding='utf-8')
    result, answer = jrun('calls://proj?callees=pkg/util.py:fmt')
    assert result.returncode == 0, result.stderr
    assert answer['target'] == 'pkg/util.py:fmt'
    assert [(Path(m['file']).name, m['calls']) for m in answer['matches']] == [('util.py', ['leaf', 'requests.get'])]
    walked, walked_answer = jrun('calls://proj?callees=pkg/util.py:fmt&depth=2')
    assert walked.returncode == 0, walked.stderr
    assert [Path(d['file']).name for d in walked_answer['definitions'] if d['level'] == 0] == ['util.py']


def test_callees_depth_text_is_a_tree_with_its_rule(project):
    result = run('calls://proj?callees=main&depth=2', '--no-gitignore')
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert any(line.startswith('Rule: callees') for line in lines), result.stdout
    assert any('helper' in line and '(expanded above)' in line for line in lines), result.stdout
    assert any('os.getenv' in line and '[external]' in line for line in lines), result.stdout
    assert NOT_MEASURED in result.stdout


# --- detail ---------------------------------------------------------------------------------

def test_detail_adds_params_and_effects(project):
    result, answer = jrun('calls://proj?callees=main&depth=2&detail')
    assert result.returncode == 0, result.stderr
    by_name = {d['name']: d for d in answer['definitions']}
    assert by_name['main']['params'] == ['key']
    assert by_name['helper']['params'] == ['x', 'y']
    assert by_name['helper']['effects'] == ['file:open']
    assert by_name['run']['effects'] == ['env:getenv']
    plain = jrun('calls://proj?callees=main&depth=2')[1]
    assert all('params' not in d and 'effects' not in d for d in plain['definitions'])


def test_detail_at_depth_one_walks_one_level(project):
    result, answer = jrun('calls://proj?callees=helper&detail')
    assert result.returncode == 0, result.stderr
    assert answer['depth'] == 1
    assert [(d['name'], d['params'], d['effects']) for d in answer['definitions']] == [('helper', ['x', 'y'], ['file:open'])]
    text = run('calls', 'proj', '--callees', 'helper', '--detail', '--no-gitignore')
    assert text.returncode == 0, text.stderr
    assert 'params: x, y' in text.stdout and 'effects: file:open' in text.stdout


# --- the rule and the declines ---------------------------------------------------------------

def test_walk_rule_states_the_callee_walk(project):
    answer = jrun('calls://proj?callees=main&depth=3')[1]
    rule = answer['walk_rule']
    assert rule['direction'] == 'callees'
    assert rule['expansion'] == 'by_definition_shallowest'
    assert rule['edges'] == 'every_call_site_per_definition'
    assert rule['resolution'] == ['language_family', 'same_file_or_import', 'ambiguous']
    assert rule['depth'] == 3 and rule['builtins'] == 'hidden'
    assert rule['measured'] == {'depth_1': True, 'beyond_depth_1': False, 'detail': False}
    assert rule['unmeasured_languages'] == []
    assert rule['text'].startswith('Rule: callees')


@pytest.mark.parametrize('query', ['callees=main&depth=2', 'callees=helper&detail'])
def test_w_calls_9_declines_unmeasured_walks(project, query):
    result, answer = jrun(f'calls://proj?{query}')
    assert result.returncode == 0, result.stderr
    declines = [w for w in answer['meta']['warnings'] if w.get('code') == 'W-CALLS-9']
    assert len(declines) == 1 and NOT_MEASURED in declines[0]['message']
    text = run(f'calls://proj?{query}', '--no-gitignore')
    assert text.stdout.count(NOT_MEASURED) == 1


@pytest.mark.parametrize('query', ['callees=main', 'target=helper', 'target=helper&depth=2'])
def test_measured_answers_carry_no_decline(project, query):
    result, answer = jrun(f'calls://proj?{query}')
    assert result.returncode == 0, result.stderr
    assert 'W-CALLS-9' not in warning_codes(answer) and 'W-CALLS-10' not in warning_codes(answer)
    assert isinstance(answer['meta']['confidence'], float)


@pytest.mark.parametrize('with_python', [False, True])
def test_unmeasured_language_gets_null_confidence_and_is_named(project, with_python):
    root = project / 'ex'
    root.mkdir()
    (root / 'm.ex').write_text(ELIXIR, encoding='utf-8')
    if with_python:
        (root / 'p.py').write_text('def run():\n    return 1\n', encoding='utf-8')
    result, answer = jrun('calls://proj/ex?callees=run')
    assert result.returncode == 0, result.stderr
    assert answer['meta']['confidence'] is None
    declines = [w for w in answer['meta']['warnings'] if w.get('code') == 'W-CALLS-10']
    assert len(declines) == 1 and declines[0]['languages'] == ['elixir']
    assert 'elixir' in declines[0]['message']
    text = run('calls://proj/ex?callees=run', '--no-gitignore')
    assert 'elixir' in text.stdout and 'no recall snapshot' in text.stdout
    walked = jrun('calls://proj/ex?callees=run&depth=2')[1]
    assert walked['walk_rule']['unmeasured_languages'] == ['elixir']


def test_the_snapshot_languages_are_the_confidence_table():
    from reveal.adapters.calls.confidence import SNAPSHOT_LANGUAGES
    from reveal.defaults import CALL_GRAPH_EXTRACTION_CONFIDENCE
    assert SNAPSHOT_LANGUAGES == frozenset(CALL_GRAPH_EXTRACTION_CONFIDENCE)


# --- absent names ---------------------------------------------------------------------------

@pytest.mark.parametrize('query', ['callees=nothere', 'callees=nothere&depth=2', 'callers=nothere',
                                   'target=nothere&depth=2', 'callees=app.py:fmt'])
def test_absent_name_exits_two_and_keeps_the_answer(project, query):
    result, answer = jrun(f'calls://proj?{query}')
    assert result.returncode == 2, result.stderr
    assert answer['type'] in ('calls_query', 'calls_callees')
    assert 'not found in' in answer['error'] and 'not found in' in result.stderr
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('query', ['target=lonely', 'target=getenv'])
def test_a_defined_or_called_name_is_not_absent(project, query):
    # lonely is defined and never called; getenv has a call site and no definition here.
    result, answer = jrun(f'calls://proj?{query}')
    assert result.returncode == 0, result.stderr
    assert 'error' not in answer


def test_absent_name_with_lost_evidence_exits_three(project, monkeypatch):
    lost = project / 'lost'
    lost.mkdir()
    (lost / 'gone.py').write_text('def nothere():\n    return 1\n', encoding='utf-8')
    real = os.scandir

    def scandir(path='.'):
        if Path(path).resolve() == lost.resolve():
            raise PermissionError(13, 'denied for the test', str(path))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    for query in ('callees=nothere', 'target=nothere'):
        result, answer = jrun(f'calls://proj?{query}')
        assert result.returncode == 3, (query, result.stderr)
        assert 'error' not in answer


def test_mcp_absent_name_is_a_tool_error_and_a_present_one_answers(project):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    absent = reveal_query(f'calls://{project.as_posix()}?callees=nothere')
    assert isinstance(absent, _ToolFailure)
    assert "Function 'nothere' not found" in str(absent)
    present = reveal_query(f'calls://{project.as_posix()}?callers=helper')
    assert not isinstance(present, _ToolFailure)
    assert 'Callers of: helper' in present


# --- callees text shows every disclosure ----------------------------------------------------

@pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')
def test_callees_text_says_what_gitignore_hid(tmp_path, monkeypatch):
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    root = tmp_path / 'repo'
    (root / 'gen').mkdir(parents=True)
    subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True, timeout=30)
    (root / '.gitignore').write_text('gen/\n', encoding='utf-8')
    (root / 'gen' / 'a.py').write_text(APP, encoding='utf-8')
    for query in ('callees=main', 'callees=main&depth=2'):
        result = run(f'calls://{(root / "gen").as_posix()}?{query}')
        assert result.returncode == 0, result.stderr  # hidden is not absent
        assert result.stdout.count(HINT) == 1, result.stdout


# --- BACK-2102: path:name shorthand with an explicit mode -----------------------------------

@pytest.mark.parametrize('query', ['callees=helper', 'callers=helper', 'rank=callers'])
def test_shorthand_with_an_explicit_mode_is_rejected(project, query):
    result, answer = jrun(f'calls://proj/app.py:main?{query}')
    assert result.returncode == 2, result.stderr
    assert 'app.py:main' in answer['error'] and 'one mode per request' in answer['error']


def test_shorthand_alone_still_selects_callers(project):
    result, answer = jrun('calls://proj/app.py:helper')
    assert result.returncode == 0, result.stderr
    assert (answer['type'], answer['target'], answer['total_callers']) == ('calls_query', 'helper', 2)


# --- the depth warning (BACK-1504) now covers only the modes that take no depth ----------------

def test_depth_with_a_mode_that_takes_none_still_warns(project):
    result = run('calls://proj?rank=callers&depth=2', '--no-gitignore')
    assert result.returncode == 0, result.stderr
    assert "Query param 'depth' for calls:// applies to ?callers, ?callees and ?root only" in result.stderr
