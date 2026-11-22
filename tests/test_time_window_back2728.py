"""One time window (COMMAND_MODEL "Time window", Scott 2026-11-22, BACK-2728).

``--since``/``--until`` take one grammar on every noun that reads them (Claude, Codex, Git, Metrics), checked before
analysis by the one shared codec declared on each control: ``today``, a period (``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``)
or a time (``YYYY-MM-DD[T ]HH:MM[:SS[.f]]``, an optional ``Z`` or ``+HH:MM``/``-HH:MM``), calendar-valid. Anything
else is an invalid request, exit 2 naming the control and the forms. The codec never changes a valid value's text:
each noun keeps its comparison, and ``today`` is the local date on every noun.

Before (measured at ad5611d9): Claude, Codex and Git compared a malformed bound as text (``--since bogus`` answered no
rows, ``--until bogus`` every row, exit 0); Git's ``--since today`` compared the word ``today`` with the commit dates,
a false zero; Metrics accepted only what ``datetime.fromisoformat`` reads, so it refused ``today`` and periods and
accepted the basic (``20260201``), week (``2026-W05``) and hour-only (``2026-02-01T12``) forms the other nouns would
compare wrongly. Conformance column 25 holds the refusal on every transport; this file holds the meanings.
"""
import json
import time
from datetime import date

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.base import get_adapter_class
from reveal.cli.invocation import COMMANDS
from reveal.cli.routing.declared import declared_adapter_class

pygit2 = pytest.importorskip('pygit2')

# The value shapes the suite gives these controls as valid (BACK-2728 S1 inventory): each binds as written.
VALID = ('2020-01-01', '2030-01-01', 'today', '2026-01-01', '2023-11-15', '2021', '2020', '2026-01',
         '2026-01-15T14:00:00.50+02:00', '2026-01-15T00:00:00.1234-1200', '2026-01-15T12:00:00Z', '2099-01-01',
         '1900-01-01', '2024-05-23', '2026-02-01 12:00:00', '2026-02-01T12:00', '2026-02-01 11:59:59')
# Of those, the ones Metrics read before (fromisoformat): today and the periods are new there.
METRICS_BEFORE = tuple(value for value in VALID if value != 'today' and len(value) > 7)
TIME_WINDOWS = (('claude', 'since'), ('claude', 'until'), ('codex', 'since'), ('codex', 'until'), ('git', 'since'),
                ('git', 'until'), ('metrics', 'since'))


def _spec(noun, control):
    adapter = declared_adapter_class(noun) if noun in COMMANDS else get_adapter_class(noun)
    return next(spec for spec in adapter.PARAM_SPECS if spec.name == control)


def _commit(repo, root, name, text, when, parents):
    (root / name).write_text(text, encoding='utf-8')
    repo.index.add(name)
    repo.index.write()
    signature = pygit2.Signature('Fixture', 'fixture@example.com', when, 0)
    return repo.create_commit('HEAD', signature, signature, f'touch {name}', repo.index.write_tree(), parents)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """A repository with a commit in November 2023 and one made now (today, local time), both touching a function
    complex enough to rank as a hotspot, so the churn walk's commit count shows where it started."""
    root = tmp_path / 'proj'
    root.mkdir()
    repo = pygit2.init_repository(str(root))
    branches = ''.join(f'    if x == {k}:\n        return {k}\n' for k in range(14))
    old = _commit(repo, root, 'app.py', f'def serve(x):\n{branches}    return -1\n', 1700000000, [])
    _commit(repo, root, 'app.py', f'def serve(x):\n{branches}    return -2\n', int(time.time()), [old])
    monkeypatch.chdir(tmp_path)
    return root


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _without_warnings(doc):
    return {key: value for key, value in doc.items() if key != 'meta'}


def test_today_on_git_answers_the_commits_made_today(proj):
    """Git compared the word ``today`` with the commit dates as text, so ``--since today`` answered no commit."""
    run, doc = _json('git', 'proj', '--view', 'history', '--since', 'today')
    assert run.returncode == 0, run.stderr
    assert [commit['message'].strip() for commit in doc['history']] == ['touch app.py'], doc['history']
    resolved, explicit = _json('git', 'proj', '--view', 'history', '--since', date.today().isoformat())
    assert _without_warnings(doc) == _without_warnings(explicit)
    run, doc = _json('git', 'proj', '--view', 'history', '--since', '2020')  # negative control: a period, unchanged
    assert run.returncode == 0 and len(doc['history']) == 2


def _churned(doc):
    return [hotspot['details']['commit_count'] for hotspot in doc['hotspots']]


@pytest.mark.parametrize('period,start,commits', [('2023', '2023-01-01', 2), ('2024', '2024-01-01', 1),
                                                  ('2023-11', '2023-11-01', 2), ('2023-12', '2023-12-01', 1)])
def test_a_period_bounds_the_metrics_churn_walk_from_its_start(proj, period, start, commits):
    """Metrics refused a period (``fromisoformat``); the churn walk needs an instant, so it takes the period's start."""
    run, doc = _json('metrics', 'proj', '--view', 'hotspots', '--since', period)
    assert run.returncode == 0, run.stderr
    _base, explicit = _json('metrics', 'proj', '--view', 'hotspots', '--since', start)
    assert doc == explicit and _churned(doc) == [commits]


def test_today_bounds_the_metrics_churn_walk_from_todays_start(proj):
    run, doc = _json('metrics', 'proj', '--view', 'hotspots', '--since', 'today')
    assert run.returncode == 0, run.stderr
    _base, explicit = _json('metrics', 'proj', '--view', 'hotspots', '--since', date.today().isoformat())
    assert doc == explicit and _churned(doc) == [1]
    _base, unbounded = _json('metrics', 'proj', '--view', 'hotspots')
    assert _churned(unbounded) == [2]  # the control: without a bound the walk counts both commits


@pytest.mark.parametrize('value', ['20260201', '2026-W05', '2026-02-01T12', 'Today', '2026-1-1', ''])
def test_metrics_narrows_to_the_one_grammar(proj, value):
    """The forms only ``fromisoformat`` read (basic, week, hour-only) compare wrongly on Claude and Codex: one grammar
    refuses them on every noun (ruling D-2728-1 (c)); a misspelt ``today`` and an unpadded date are malformed too."""
    run, doc = _json('metrics', 'proj', '--view', 'hotspots', '--since', value)
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert 'since must be today' in run.stderr and 'YYYY-MM-DD' in run.stderr, run.stderr


@pytest.mark.parametrize('noun,control', TIME_WINDOWS)
@pytest.mark.parametrize('value', VALID)
def test_every_valid_shape_binds_as_written(noun, control, value):
    """The codec returns the text unchanged, so each noun's own comparison reads what it read before (positive control:
    passes before the codec, except Metrics' today and periods)."""
    if noun == 'metrics' and value not in METRICS_BEFORE:
        pytest.skip('new on metrics: test_a_period_bounds... and test_today_bounds...')
    assert _spec(noun, control).validate(value) == value


@pytest.mark.parametrize('value', VALID)
def test_every_valid_shape_answers_on_git(proj, value):
    run, _doc = _json('git', 'proj', '--view', 'history', '--since', value)
    assert run.returncode == 0, run.stderr


@pytest.mark.parametrize('control', ['since', 'until'])
def test_the_refusal_names_the_control_and_every_form(proj, control):
    run, _doc = _json('git', 'proj', '--view', 'history', f'--{control}', '2026-02-30')
    assert run.returncode == 2
    assert (f"{control} must be today, a period (YYYY, YYYY-MM or YYYY-MM-DD) or a time "
            f"(YYYY-MM-DD[T ]HH:MM[:SS[.f]], optional Z, +HH:MM or -HH:MM), got '2026-02-30'") in run.stderr, run.stderr


def test_an_equal_typed_list_is_one_bound_and_two_bounds_conflict(proj):
    """COMMAND_MODEL "Conflicting values" on the typed API, on every time window as Git already did: Claude, Codex and
    Metrics refused a list of equal bounds as 'not a valid string'."""
    from reveal.errors import RequestValidationError
    spec = _spec('claude', 'since')
    assert spec.validate(['2026-01-01', '2026-01-01']) == '2026-01-01'
    with pytest.raises(ValueError, match="'2026-01-01' and '2026-02-01'"):
        spec.validate(['2026-01-01', '2026-02-01'])
    from reveal.api import query
    with pytest.raises(RequestValidationError, match='since'):
        query('metrics', 'proj', view='hotspots', since=['2023-01-01', '2024-01-01'])


def test_packs_since_is_a_git_ref_and_not_a_time(proj):
    """Negative control: Pack's ``since`` names a ref (its --against package), so the codec never reaches it."""
    run, doc = _json('pack', 'proj', '--since', 'HEAD~1')
    assert run.returncode == 0, run.stderr
    assert doc['meta'].get('since') == 'HEAD~1' and not doc['meta'].get('since_error'), doc['meta']
    run, doc = _json('pack', 'proj', '--since', 'bogus')
    assert run.returncode == 0 and doc['meta'].get('since_error'), doc['meta']
