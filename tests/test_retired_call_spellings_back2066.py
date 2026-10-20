"""The old call-graph spellings print a "replaced by" note and keep their answer (BACK-2066 slice D).

Phase 2b merged trace into calls. The older spellings stay for the note period (release strategy D5)
and go through the one ``RETIREMENTS`` table:

- ``reveal trace`` and ``trace://`` -> ``calls ?callees=FUNC&depth=N&detail`` (trace keeps its
  frames shape until the cut, decision c);
- ``calls ?root=`` / ``--root`` -> ``?callees=FUNC&depth=N``;
- ``calls ?target=`` / ``--target`` -> ``?callers=FUNC`` (an alias with a note, decision a);
- ``ast://?calls=``, ``?callee_of=`` and ``?show=calls`` -> calls ``?callers=`` / ``?callees=`` or
  ``--grep`` (decision e: retired, not kept as element filters).

Each prints one note on stderr, answers exactly as with the row removed, and carries one
``retired_spelling`` warning in JSON and MCP. The MCP tool ``reveal_trace`` keeps its name and
prints no note until Phase 7 (decision g); ``depends://?root=`` is another parameter and is
untouched.
"""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.cli.invocation import RETIREMENTS, Retirement

APP = '''\
def helper(x):
    return x + 1


def run(v):
    print(v)
    return helper(v)


def main():
    run(1)
    return helper(2)
'''


@pytest.fixture
def project(tmp_path):
    proj = tmp_path / 'proj'
    proj.mkdir()
    (proj / 'app.py').write_text(APP, encoding='utf-8')
    return str(proj)


# case id -> (table key, argv builder, a substring the replacement must name)
CASES = {
    'reveal trace': ('subcommand:trace', lambda p: ['trace', p, '--from', 'main'], '--callees'),
    'trace://': ('scheme:trace', lambda p: [f'trace://{p}?from=main'], '?callees='),
    'calls ?root=': ('param:calls.root', lambda p: [f'calls://{p}?root=main'], '?callees='),
    'reveal calls --root': ('param:calls.root', lambda p: ['calls', p, '--root', 'main'], '--callees'),
    'calls ?target=': ('param:calls.target', lambda p: [f'calls://{p}?target=helper'], '?callers='),
    'reveal calls --target': ('param:calls.target', lambda p: ['calls', p, '--target', 'helper'], '--callers'),
    'ast ?calls=': ('param:ast.calls', lambda p: [f'ast://{p}?calls=helper'], '?callers='),
    'ast ?callee_of=': ('param:ast.callee_of', lambda p: [f'ast://{p}?callee_of=main'], '?callees='),
    'ast ?show=calls': ('value:ast.show=calls', lambda p: [f'ast://{p}?show=calls'], '?callers='),
}

# The spellings that replace them, and siblings that share a parameter or scheme name: none notes.
NOT_RETIRED = {
    'calls ?callees=&depth=': lambda p: [f'calls://{p}?callees=main&depth=2'],
    'calls ?callers=': lambda p: [f'calls://{p}?callers=helper'],
    'reveal calls --callers': lambda p: ['calls', p, '--callers', 'helper'],
    'reveal calls --callees --depth': lambda p: ['calls', p, '--callees', 'main', '--depth', '2'],
    'depends ?root=': lambda p: [f'depends://{p}?root={p}'],
    'ast ?callers>N': lambda p: [f'ast://{p}?callers>0'],
    'ast ?show=dict-heatmap': lambda p: [f'ast://{p}?show=dict-heatmap'],
    'ast ?name=': lambda p: [f'ast://{p}?name=helper'],
}


def _retired(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


def _without_retirement(doc):
    """The answer minus the retirement fact, an emptied warnings list or meta dropped; applied to both
    sides, since some answers carry an empty warnings list of their own."""
    meta = doc.get('meta')
    if isinstance(meta, dict) and 'warnings' in meta:
        meta['warnings'] = [w for w in meta['warnings'] if w.get('code') != 'retired_spelling']
        if not meta['warnings']:
            del meta['warnings']
        if not meta:
            del doc['meta']
    return doc


def _unretired(monkeypatch, key):
    """What the spelling answered before its row existed."""
    monkeypatch.delitem(RETIREMENTS, key, raising=False)


@pytest.mark.parametrize('case', CASES)
def test_a_retired_call_spelling_prints_one_note_and_keeps_its_answer(monkeypatch, project, case):
    key, argv, _ = CASES[case]
    argv = argv(project)
    text_run = run(*argv)
    json_run = run(*argv, '--format', 'json')
    text = RETIREMENTS[key].text if key in RETIREMENTS else f'<no {key} row>'

    # One note and nothing else deprecated: reveal trace is not also noted as trace://.
    assert text_run.stderr.count(f'note: {text}') == 1, text_run.stderr
    assert json_run.stderr.count(f'note: {text}') == 1, json_run.stderr
    assert text_run.stderr.count('deprecated') == json_run.stderr.count('deprecated') == 1
    assert [w['field'] for w in _retired(json.loads(json_run.stdout))] == [key]

    with monkeypatch.context() as m:
        _unretired(m, key)
        base_text = run(*argv)
        base_json = run(*argv, '--format', 'json')
    assert 'deprecated' not in base_text.stderr
    assert text_run.returncode == base_text.returncode == 0
    assert json_run.returncode == base_json.returncode == 0
    assert text_run.stdout == base_text.stdout
    assert _without_retirement(json.loads(json_run.stdout)) == _without_retirement(json.loads(base_json.stdout))


@pytest.mark.parametrize('case', CASES)
def test_the_note_names_the_replacement(case):
    key, _, names = CASES[case]
    assert key in RETIREMENTS, key
    assert RETIREMENTS[key].stage == 'note'
    assert names in RETIREMENTS[key].replacement, RETIREMENTS[key].text


@pytest.mark.parametrize('key', ['param:ast.calls', 'value:ast.show=calls'])
def test_the_ast_call_filter_notes_point_at_grep_too(key):
    """Decision (e): calls= also matched globs; --grep is what answers a pattern now."""
    assert '--grep' in RETIREMENTS[key].replacement


@pytest.mark.parametrize('case', NOT_RETIRED)
def test_the_replacements_and_their_siblings_print_no_note(project, case):
    result = run(*NOT_RETIRED[case](project), '--format', 'json')
    assert 'deprecated' not in result.stderr, result.stderr
    assert not _retired(json.loads(result.stdout))


@pytest.mark.parametrize('case', CASES)
def test_at_the_cut_each_spelling_exits_2_with_its_text(monkeypatch, project, case):
    key, argv, _ = CASES[case]
    assert key in RETIREMENTS, key
    entry = RETIREMENTS[key]
    monkeypatch.setitem(RETIREMENTS, key, Retirement(entry.old, entry.replacement, 'error'))
    result = run(*argv(project), '--format', 'json')
    assert result.returncode == 2
    assert f'error: {entry.text}' in result.stderr
    assert result.stdout == ''


# --- MCP: the note is in the tool result; reveal_trace keeps its name (decision g) -------------

MCP_CASES = {
    'trace://': ('scheme:trace', lambda p: f'trace://{p}?from=main'),
    'calls ?root=': ('param:calls.root', lambda p: f'calls://{p}?root=main'),
    'calls ?target=': ('param:calls.target', lambda p: f'calls://{p}?target=helper'),
    'ast ?calls=': ('param:ast.calls', lambda p: f'ast://{p}?calls=helper'),
}


@pytest.mark.parametrize('case', MCP_CASES)
def test_mcp_reveal_query_returns_the_note_with_the_answer(monkeypatch, project, case, capsys):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    key, uri = MCP_CASES[case]
    uri = uri(project)
    capsys.readouterr()
    out = reveal_query(uri)
    assert capsys.readouterr().err == ''
    text = RETIREMENTS[key].text if key in RETIREMENTS else f'<no {key} row>'
    assert out.count(f'[note: {text}]') == 1, out
    doc = json.loads(reveal_query(uri, provenance=True))
    assert [w['field'] for w in _retired(doc)] == [key]
    with monkeypatch.context() as m:
        _unretired(m, key)
        base = reveal_query(uri)
    assert out.startswith(base.rstrip('\n'))


def test_mcp_reveal_trace_keeps_its_name_and_prints_no_note_until_phase_7(project):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_trace
    out = reveal_trace(project, 'main')
    assert 'deprecated' not in out and '[note:' not in out
    assert out.startswith('Trace: main')


def test_mcp_reveal_trace_and_the_server_instructions_point_at_calls():
    pytest.importorskip('mcp')
    from reveal.mcp_server import mcp, reveal_trace
    doc = reveal_trace.__doc__ or ''
    assert 'calls://' in doc and 'callees=' in doc, doc
    item6 = next(line for line in mcp.instructions.split('\n') if line.startswith('6. '))
    assert 'callees=' in item6, item6
