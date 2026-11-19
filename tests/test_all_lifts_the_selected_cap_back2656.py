"""``--all`` lifts the cap of the selected answer only (Scott 2026-11-18, COMMAND_MODEL "Applicability", BACK-2656).

On an answer with no row cap the request is already every row: ``--all`` is satisfied, so it answers exactly as
without it, exit 0 and no note (never exit 2, never an unused-flag note), on every declared noun, on the URI and the
subcommand. On an answer with a cap it lifts that cap. One shared rule: the cap ``--all`` binds is the selected
answer's, judged with the answer's own declarations (``ParamSpec.answers``), never a per-noun special case.
"""
import json

import pytest

from conftest import _run_reveal_direct
from test_vocabulary_conformance_back2654 import (ANSWER_TARGETS, BASE, NOUNS, TARGETS, _answers, _run,  # noqa: F401
                                                  workspace)

_ALL_NOTES = ('unused_flag', 'unused_query_param', 'control_unread_by_data')


def _doc(run):
    return json.loads(run.out) if run.out.strip().startswith('{') else {}


def _all_noted(run):
    """Whether *run* says --all (or a control it injected) went unused."""
    warnings = (_doc(run).get('meta') or {}).get('warnings') or []
    if any((w.get('code') or w.get('type')) in _ALL_NOTES for w in warnings):
        return True
    return '--all' in run.err and ('no effect' in run.err or 'not read' in run.err)


def _without_volatile(doc):
    doc = json.loads(json.dumps(doc))
    for key in ('execution', 'timing', 'elapsed', 'generated_at'):
        doc.pop(key, None)
    meta = doc.get('meta') if isinstance(doc.get('meta'), dict) else {}
    meta.pop('timing', None)
    return doc


def _cases():
    for noun in sorted(set(NOUNS) - {'stats'}):
        for target in ANSWER_TARGETS.get(noun, (TARGETS.get(noun, 'proj'),)):
            for label, parts in _answers(noun):
                yield pytest.param(noun, target, parts, id=f'{noun}-{target or "root"}-{label}')


@pytest.mark.parametrize('noun,target,parts', list(_cases()))
def test_all_never_refuses_or_notes_an_answer(workspace, noun, target, parts):  # noqa: F811
    """Every answer of every declared noun: --all answers (no exit 2) and says nothing about itself; where the answer
    has no cap it is the same answer as without --all."""
    uri = f'{noun}://{target}' + (f"?{'&'.join(parts)}" if parts else '')
    plain = _run(uri, '--format', 'json')
    if plain.rc not in (0, 1, 3):
        pytest.skip(f'not an answer on this resource: {plain.brief()}')
    lifted = _run(uri, '--all', '--format', 'json')
    assert lifted.rc == plain.rc, (lifted.brief(), plain.brief())
    assert not _all_noted(lifted), lifted.brief()


# --- positive controls: a capped answer has its cap lifted ------------------------------------------------------

@pytest.fixture
def many(tmp_path, monkeypatch):
    """Twelve functions each called once, and twelve modules each imported once: more rows than any default cap."""
    names = [f'f{index:02d}' for index in range(12)]
    body = ''.join(f'def {name}():\n    return 1\n\n\n' for name in names)
    body += 'def main():\n' + ''.join(f'    {name}()\n' for name in names)
    (tmp_path / 'app.py').write_text(body, encoding='utf-8')
    for name in names:
        (tmp_path / f'm{name}.py').write_text('X = 1\n', encoding='utf-8')
    (tmp_path / 'hub.py').write_text(''.join(f'import m{name}\n' for name in names), encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _rows(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 0, (argv, run.stderr)
    doc = json.loads(run.stdout)
    assert not [w for w in doc['meta'].get('warnings', []) if w.get('code') in _ALL_NOTES], doc['meta']
    return doc


@pytest.mark.parametrize('form', [('calls://.?sort=-callers',), ('calls', '.', '--sort=-callers')])
def test_all_lifts_the_calls_ranking_cap(many, form):
    capped, lifted = _rows(*form), _rows(*form, '--all')
    assert len(capped['entries']) == 10 < len(lifted['entries'])  # the ranking's default cap is 10


@pytest.mark.parametrize('form', [('calls://.?callers=f01',), ('calls', '.', '--callers', 'f01'),
                                  ('calls://.?callees=main',), ('calls://.?modules',)])
def test_all_is_quiet_on_a_calls_answer_with_no_cap(many, form):
    plain, lifted = _rows(*form), _rows(*form, '--all')
    assert _without_volatile(lifted) == _without_volatile(plain)


@pytest.mark.parametrize('form', [('imports://.?sort=-fan-in',), ('imports', '.', '--sort=-fan-in'),
                                  ('imports://.',), ('imports', '.', '--circular')])
def test_all_on_imports_answers_every_row_quietly(many, form):
    """The fan-in ranking shows every row unless limit caps it: --all answers that, with no note (it was noted
    unused); the other views have no row cap."""
    plain, lifted = _rows(*form), _rows(*form, '--all')
    assert _without_volatile(lifted) == _without_volatile(plain)
    if 'fan' in ' '.join(form):
        assert len(lifted['entries']) == lifted['total'] > 10


@pytest.mark.parametrize('form', [('json', 'data.json'), ('json://data.json',), ('json://rows.json',),
                                  ('json://rows.json?view=keys',)])
def test_all_is_quiet_on_json(tmp_path, monkeypatch, form):
    (tmp_path / 'data.json').write_text('{"a": 1}', encoding='utf-8')
    (tmp_path / 'rows.json').write_text('[{"n": 1}, {"n": 2}]', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    plain, lifted = _rows(*form), _rows(*form, '--all')
    assert _without_volatile(lifted) == _without_volatile(plain)


def test_all_beside_a_different_cap_still_conflicts(many):
    run = _run_reveal_direct('calls', '.', '--sort=-callers', '--limit', '3', '--all', '--format', 'json')
    assert run.returncode == 2 and '--all' in run.stderr, run.stderr
