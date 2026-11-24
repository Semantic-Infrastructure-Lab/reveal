"""Calls ``detail`` is the string control normal|full, the one scale every noun's detail is on (BACK-2774 ruling S1).

Calls declared ``detail`` as a boolean (valueless ``--detail``, ``?detail``, ``true``/``false``, with ``normal``/``full``
read as false/true) while every other noun's ``detail`` is a level of the one scale (COMMAND_MODEL "How much of it",
which retires the valueless ``detail``). Column 29 of the conformance test recorded it ``not_yet``. Now:

- ``--detail normal|full`` (default normal) answers equally on the CLI, the URI, ``api.query`` and MCP;
- the valueless ``--detail``/``?detail``/``detail=True`` and ``true``/``false`` answer as ``full``/``normal`` with the
  generated replaced-by note (``value:calls.detail=true|false``; a URI request's one request note names ``--detail
  full`` instead, BACK-2716), until the cut;
- any other value exits 2 naming ``normal`` and ``full`` (``yes`` used to answer as true, ``bogus`` named a boolean);
- the readers read the level: ``detail=normal`` with ``format=dot`` is the depth-1 list (no graph), as no detail is.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct as run  # noqa: E402
from conftest import is_request_note  # noqa: E402

from reveal.adapters.calls.adapter import CallsAdapter  # noqa: E402
from reveal.api import query  # noqa: E402
from reveal.errors import RequestValidationError  # noqa: E402

pytestmark = [pytest.mark.unit]

LEVEL_OF = {'true': 'full', 'false': 'normal'}


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'app.py').write_text(
        'import os\n\n\ndef sink(value):\n    print(value)\n    return os.environ.get("X")\n\n\n'
        'def middle(item):\n    return sink(item)\n\n\ndef top(items):\n    return middle(items)\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    return root


def uri(controls):
    return f'calls://proj?{controls}'


def cli_json(*args):
    result = run(*args, '--format', 'json')
    return result, (json.loads(result.stdout) if result.stdout.strip() else None)


def retired(answer):
    return [w for w in answer['meta']['warnings'] if w.get('type') == 'retired_spelling']


def without_retired(answer):
    result = copy.deepcopy(answer)
    result['meta']['warnings'] = [w for w in result['meta']['warnings'] if w.get('type') != 'retired_spelling']
    result.pop('execution', None)
    return result


def mcp_json(address):
    from reveal.mcp_server import _ToolFailure, reveal_query
    result = reveal_query(address, provenance=True)
    assert not isinstance(result, _ToolFailure), result
    return json.loads(result)


def canonical(level):
    result, answer = cli_json('calls', 'proj', '--callees', 'top', '--detail', level)
    assert result.returncode == 0, result.stderr
    assert not retired(answer)
    return answer


# --- the declaration ----------------------------------------------------------------------------------------------

def test_detail_is_the_string_control_normal_or_full():
    spec = next(spec for spec in CallsAdapter.PARAM_SPECS if spec.name == 'detail')
    assert (spec.type, spec.choices, spec.default, spec.repeatable) == ('string', ('normal', 'full'), 'normal', False)
    result, schema = cli_json('help://schemas/calls')
    assert result.returncode == 0, result.stderr
    detail = schema['query_params']['detail']
    assert (detail['type'], detail['choices'], detail['default']) == ('string', ['normal', 'full'], 'normal')


# --- the canonical levels: one answer on every transport ------------------------------------------------------------

@pytest.mark.parametrize('transport', ['cli', 'uri', 'api', 'mcp'])
@pytest.mark.parametrize('level', ['normal', 'full'])
def test_a_level_answers_equally_on_every_transport(project, transport, level):
    expected = canonical(level)
    assert bool(expected.get('levels')) == (level == 'full')
    if transport == 'cli':
        actual = expected
    elif transport == 'uri':
        result, actual = cli_json(uri(f'callees=top&detail={level}'))
        assert result.returncode == 0, result.stderr
    elif transport == 'api':
        actual = query(uri('callees=top'), detail=level)
    else:
        actual = mcp_json(uri(f'callees=top&detail={level}'))
    assert without_retired(actual) == without_retired(expected)


def test_normal_is_the_default(project):
    result, plain = cli_json('calls', 'proj', '--callees', 'top')
    assert result.returncode == 0
    assert without_retired(plain) == without_retired(canonical('normal'))


def test_normal_text_prints_no_detail(project):
    plain = run('calls', 'proj', '--callees', 'top', '--depth', '2')
    normal = run('calls', 'proj', '--callees', 'top', '--depth', '2', '--detail', 'normal')
    full = run('calls', 'proj', '--callees', 'top', '--depth', '2', '--detail', 'full')
    assert plain.returncode == normal.returncode == full.returncode == 0
    assert normal.stdout == plain.stdout
    assert 'params:' not in normal.stdout and 'params:' in full.stdout


# --- the retired spellings: the same answer with a replaced-by note -------------------------------------------------

@pytest.mark.parametrize('flags,word', [(('--detail',), 'true'), (('--detail', 'true'), 'true'),
                                        (('--detail=true',), 'true'), (('--detail', 'false'), 'false'),
                                        (('--detail=false',), 'false')],
                         ids=['bare', 'true', 'true-equals', 'false', 'false-equals'])
def test_a_retired_cli_spelling_answers_as_its_level_with_its_note(project, flags, word):
    result, answer = cli_json('calls', 'proj', '--callees', 'top', *flags)
    assert result.returncode == 0, result.stderr
    assert without_retired(answer) == without_retired(canonical(LEVEL_OF[word]))
    notes = retired(answer)
    assert [w['field'] for w in notes] == [f'value:calls.detail={word}']
    assert notes[0]['replacement'].startswith(f'--detail {LEVEL_OF[word]}')
    text = run('calls', 'proj', '--callees', 'top', *flags)
    assert f'use --detail {LEVEL_OF[word]}' in text.stderr


@pytest.mark.parametrize('controls,level', [('callees=top&detail', 'full'), ('callees=top&detail=true', 'full'),
                                            ('callees=top&detail=false', 'normal')],
                         ids=['bare', 'true', 'false'])
def test_a_retired_uri_spelling_answers_as_its_level_and_its_request_note_names_the_level(project, controls, level):
    expected = without_retired(canonical(level))
    result, answer = cli_json(uri(controls))
    assert result.returncode == 0, result.stderr
    assert without_retired(answer) == expected
    for actual in (answer, query(uri(controls)), mcp_json(uri(controls))):
        assert without_retired(actual) == expected
        notes = [w['message'] for w in retired(actual) if is_request_note(w)]
        assert len(notes) == 1, retired(actual)
        assert '--detail true' not in notes[0] and '--detail false' not in notes[0]
        assert not notes[0].rstrip('.').endswith('--detail'), notes[0]
        if level == 'full':
            assert '--detail full' in notes[0], notes[0]


@pytest.mark.parametrize('typed,level', [(True, 'full'), (False, 'normal'), ('true', 'full'), ('false', 'normal')])
def test_a_retired_python_keyword_answers_as_its_level(project, typed, level):
    actual = query(uri('callees=top'), detail=typed)
    assert without_retired(actual) == without_retired(query(uri('callees=top'), detail=level))
    notes = [w['message'] for w in retired(actual) if is_request_note(w)]
    assert len(notes) == 1 and '--detail true' not in notes[0] and not notes[0].rstrip('.').endswith('--detail')


# --- a value outside the scale exits 2 naming it ---------------------------------------------------------------------

@pytest.mark.parametrize('value', ['bogus', 'yes', '1', 'summary', 'raw'])
def test_a_value_outside_normal_and_full_exits_2_naming_them(project, value):
    for argv in (('calls', 'proj', '--callees', 'top', '--detail', value), (uri(f'callees=top&detail={value}'),)):
        result = run(*argv)
        assert result.returncode == 2, (argv, result.returncode, result.stdout[:200])
        assert 'normal' in result.stderr and 'full' in result.stderr, result.stderr
    with pytest.raises(RequestValidationError, match='normal'):
        query(uri('callees=top'), detail=value)


def test_detail_outside_callees_still_exits_2(project):
    result = run('calls', 'proj', '--callers', 'sink', '--detail', 'full')
    assert result.returncode == 2
    assert "control 'detail' is not read by this answer" in result.stderr


# --- the readers read the level ----------------------------------------------------------------------------------------

def test_detail_normal_with_dot_is_the_depth_1_list_which_draws_no_graph(project):
    refused = run(uri('callees=top&format=dot'))
    normal = run(uri('callees=top&detail=normal&format=dot'))
    assert refused.returncode == 2 and 'callees at depth 1 has none' in refused.stderr
    assert normal.returncode == 2 and 'callees at depth 1 has none' in normal.stderr, normal.stdout[:300]
    drawn = run(uri('callees=top&detail=full&format=dot'))
    assert drawn.returncode == 0 and drawn.stdout.startswith('digraph'), drawn.stderr
