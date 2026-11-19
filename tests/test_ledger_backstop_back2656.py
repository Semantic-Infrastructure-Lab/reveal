"""The unused-input ledger is the backstop of the applicability declarations (Scott 2026-11-18, BACK-2656 Step 0 Q3).

Every declared noun's answers (each operation selection, on each resource whose path selects an answer) are given each
control their declarations say they read (``ParamSpec.answers``, judged by the shared ``answer_reads_control``), with a
value other than the control's default. The request either answers, and then the ledger must not report the control
unread (its warning stays on declared nouns, reachable only through a wrong declaration), or it is an invalid request
for another reason (a value rule, a requirement, a conflict), which this test does not judge. A control the
declarations say is read must never be refused as unread, and one they say is not read must never answer: the
predictor and the check agree. The matrix is built from the declarations and the conformance probe's answers and targets, not typed here.

Not judged here: ``where`` and the walk policy (``_NOT_PROBED``: rules 3 and 8 own the filter's fields), and whether a
read control changes the answer (a read-but-not-applied drop the ledger cannot see; see the BACK-2656 Step 4 report).
"""
import pytest

from reveal.adapters.factory import answer_reads_control
from reveal.utils.query_parser import query_key
from test_vocabulary_conformance_back2654 import (ANSWER_TARGETS, APPLICABILITY_VALUES, NOUNS, TARGETS,  # noqa: F401
                                                  _NOT_PROBED, _adapter, _answers, _applicability_value, _run, _specs,
                                                  _unread, workspace)

# (noun, target, answer label, control) whose declared read the ledger reports unread: each names its task. The list
# only falls; an entry that stops failing must be removed.
NOT_YET: dict = {}

# Resources where the selected answer declines (not applicable, exit 0) because of the data, before it reads its
# controls: a patches scan of a file with no test file, git outside a repository (BACK-2696). Only the data decides it, so the controls are named
# in the shared control_unread_by_data warning, never by the ledger (COMMAND_MODEL "Applicability", Q2).
DECLINED_TARGETS = {'patches': ('proj/app.py',), 'git': ('home',)}  # git: a directory outside every repository


def _other_than_default(noun, spec):
    """A value the request gives on purpose: the probe's own value where it names one, else one the control's default
    is not (the negated switch, another choice, a different count; every file for exclude)."""
    if (noun, spec.name) in APPLICABILITY_VALUES:
        return APPLICABILITY_VALUES[(noun, spec.name)]
    default = spec.default
    if spec.type in ('boolean', 'flag'):
        return 'false' if default is True else 'true'
    if spec.name == 'exclude':
        return '*.py'
    others = [str(choice) for choice in spec.choices if choice not in (None, '') and str(choice) != str(default)]
    if others:
        return others[0]
    if spec.type == 'integer':
        return '1' if str(default) != '1' else '2'
    return _applicability_value(noun, spec)


def backstop_cases(noun):
    """(key, ok, detail) for every declared control on every answer of *noun* that answers on the fixture."""
    adapter = _adapter(noun)
    cases = []
    for target in (*ANSWER_TARGETS.get(noun, (TARGETS.get(noun, 'proj'),)), *DECLINED_TARGETS.get(noun, ())):
        for label, parts in _answers(noun):
            def uri(*extra):
                query = '&'.join([*parts, *extra])
                return f'{noun}://{target}' + (f'?{query}' if query else '')
            if _run(uri(), '--format', 'json').rc not in (0, 1, 3):
                continue  # not an answer on this resource
            given = {query_key(part) for part in parts}
            for spec in _specs(noun):
                if spec.role == 'operation' or spec.name in _NOT_PROBED or spec.name in given:
                    continue
                term = f'{spec.name}={_other_than_default(noun, spec)}'
                reads = answer_reads_control(adapter, spec.name, '&'.join([*parts, term]), target)
                run = _run(uri(term), '--format', 'json')
                key = (noun, target, label, spec.name)
                refused = run.rc == 2 and 'is not read by this answer' in run.err
                if refused and reads:
                    cases.append((key, False, f'declared read but {run.brief()}'))
                elif not reads:  # refused, or an invalid request for an earlier reason (a value rule): never answered
                    cases.append((key, run.rc == 2, f'declared unread but {run.brief()}'))
                elif run.rc in (0, 1, 3):
                    cases.append((key, not _unread(run, spec.name),
                                  f'{run.brief()}: declared read, and the ledger reports it unread'))
    return cases


@pytest.mark.parametrize('noun', sorted(NOUNS))
def test_a_declared_read_is_never_reported_unread(workspace, noun):  # noqa: F811
    cases = backstop_cases(noun)
    assert any(ok for _key, ok, _detail in cases), f'{noun}: no answer took a declared control'  # it measured something
    failing = {key: detail for key, ok, detail in cases if not ok}
    unexpected = {key: detail for key, detail in failing.items() if key not in NOT_YET}
    assert not unexpected, '\n'.join(f'{key}: {detail}' for key, detail in unexpected.items())
    fixed = [key for key in NOT_YET if key[0] == noun and key not in failing]
    assert not fixed, f'remove from NOT_YET, they now hold: {fixed}'


def test_the_backstop_fails_when_a_declaration_claims_a_read_the_answer_does_not_make(workspace, monkeypatch):  # noqa: F811
    """A backstop that could only pass measures nothing: declare (test-only) that Markdown's ``limit`` and ``offset``
    are read by every answer. The links and lint views do not read them; the shared check no longer refuses them, so
    the ledger reports them unread there, and the backstop names exactly those cases."""
    from dataclasses import replace
    adapter = _adapter('markdown')
    monkeypatch.setattr(adapter, 'PARAM_SPECS', tuple(replace(spec, answers=()) if spec.name in ('limit', 'offset')
                                                      else spec for spec in adapter.PARAM_SPECS))
    failing = sorted((label, control) for (_noun, _target, label, control), ok, _detail in backstop_cases('markdown')
                     if not ok)
    assert failing == [('view=links', 'limit'), ('view=links', 'offset'), ('view=lint', 'limit'),
                       ('view=lint', 'offset')], failing


def test_the_predictor_names_the_answer_of_an_empty_resource_path_as_the_check_does():
    """``codex://`` has an empty resource path: the shared check predicts its answer on that path (the session list
    when filter is given); ``answer_reads_control`` (the --all seam's predictor) must not treat '' as no path."""
    codex = _adapter('codex')
    assert answer_reads_control(codex, 'filter', 'filter=auth', '') is True
    assert answer_reads_control(codex, 'key', 'filter=auth&key=model', '') is False  # read by config only
