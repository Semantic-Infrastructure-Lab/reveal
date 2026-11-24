"""Metrics and Patches applicability (COMMAND_MODEL "Applicability", BACK-2656 Step 2c).

Each control declares the answers that read it (``ParamSpec.answers``): on any other answer it is an invalid
request, refused before analysis with the one shared message, on the URI, the subcommand, the URI with a flag and
``api.query``. Metrics' answers are the file and directory answers of the default view, the legacy ``hotspots``
ranking, ``view=hotspots`` and ``view=provenance``; Patches' are the raw scan and ``view=pressure``. Before, an unread
control answered with the ledger's unused-input note, exit 0, or with no word at all where the answer read the control
and did nothing with it (Metrics ``detail`` on ``view=hotspots``, ``code-only`` on a file, ``where`` on
``view=provenance``; Patches ``top`` on the raw scan). ``--all`` lifts the selected answer's cap only: Patches'
``view=pressure`` caps its hotspot lists with ``top``, which ``--all`` now lifts.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.errors import RequestValidationError

UNREAD_WARNINGS = ('unused_query_param', 'unused_flag', 'unknown_query_param')

_TARGETS = 25  # more patch groups than view=pressure's default top=20


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """A source file, a data file and a test file that patches each of 25 functions three times."""
    (tmp_path / 'app.py').write_text(
        'import os\n\n\n' + ''.join(f'def f{index:02d}(x):\n    if x:\n        return os.getcwd()\n    return 1\n\n\n'
                                    for index in range(_TARGETS)), encoding='utf-8')
    (tmp_path / 'conf.yaml').write_text('a: 1\nb: 2\n', encoding='utf-8')
    (tmp_path / 'tests').mkdir()
    body = 'from unittest import mock\n\nimport app\n\n\n'
    for index in range(_TARGETS):
        for case in range(3):
            body += (f"def test_f{index:02d}_{case}():\n    with mock.patch('app.f{index:02d}'):\n"
                     f"        assert app.f{index:02d}(1)\n\n\n")
    (tmp_path / 'tests' / 'test_app.py').write_text(body, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _unread(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if (w.get('code') or w.get('type'))
            in UNREAD_WARNINGS]


def _refused(argv, control, answer):
    run, _doc = _run(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout[:300], run.stderr)
    assert f"control {control} is not read by this answer ({answer}" in run.stderr, run.stderr
    assert 'controls this answer reads: ' in run.stderr, run.stderr


# --- metrics ------------------------------------------------------------------------------------------------------

_DIR, _HOT, _PROV = 'stats_summary, default', 'stats_summary, view, view=hotspots', 'classify_report, view, view=provenance'
_FILE, _FILE_LEGACY, _FILE_HOT = 'stats_file, default', 'stats_file, hotspots', 'stats_file, view, view=hotspots'


@pytest.mark.parametrize('argv,control,answer', [
    (('metrics://.?top=3',), "'top'", _DIR),                               # the ledger's note before
    (('metrics://.?churn=off',), "'churn'", _DIR),
    (('metrics://.?since=2020-01-01',), "'since'", _DIR),
    (('metrics://.?merges=off',), "'merges'", _DIR),
    (('metrics://.?tests=exclude',), "'tests'", _DIR),
    (('metrics://.?view=hotspots&sort=lines',), "'sort'", _HOT),
    (('metrics://.?view=hotspots&detail=summary',), "'detail'", _HOT),     # silent before: the ranking is the rows
    (('metrics://.?view=provenance&limit=2',), "'limit'", _PROV),
    (('metrics://.?view=provenance&code-only',), "'code-only'", _PROV),
    (('metrics://.?view=provenance&lines>5',), "'where' (lines>5)", _PROV),  # silent before
    (('metrics://app.py?limit=2',), "'limit'", _FILE),
    (('metrics://app.py?offset=1',), "'offset'", _FILE),
    (('metrics://conf.yaml?code-only',), "'code-only'", _FILE),             # silent before: a file is not walked
    (('metrics://app.py?hotspots&limit=2',), "'limit'", _FILE_LEGACY),
    (('metrics', '.', '--top', '3'), "'top'", _DIR),                         # the subcommand
    (('metrics', '.', '--no-churn'), "'churn'", _DIR),                       # a legacy spelling names its control
    (('metrics', '.', '--view', 'provenance', '--sort', 'lines'), "'sort'", _PROV),
    (('metrics', 'app.py', '--limit', '2'), "'limit'", _FILE),
    (('metrics://.', '--since', '2020-01-01'), "'since'", _DIR),             # the URI and a flag
    (('metrics://app.py', '--limit', '2'), "'limit'", _FILE),
])
def test_metrics_refuses_a_control_its_answer_does_not_read(proj, argv, control, answer):
    _refused(argv, control, answer)


@pytest.mark.parametrize('uri,answer', [
    ('metrics://.?view=provenance&exclude=tests', 'classify_report'),
    ('metrics://app.py?exclude=tests', 'stats_file'),
    ('metrics://app.py?view=hotspots&exclude=tests', 'stats_file'),
])
def test_metrics_exclude_is_the_walk_control_on_every_answer(proj, uri, answer):
    """Moved from the refusals above (BACK-2730): exclude is the shared walk control, declared as every walking noun
    declares it, so no answer refuses it as unread. The provenance walk applies it as --exclude did, and a file target
    satisfies it (D-2730-2 (a)): metrics answers alike on the flag and the URI."""
    run, doc = _run(uri)
    assert run.returncode == 0, (run.returncode, run.stderr)
    assert doc['type'] == answer


def test_metrics_api_refuses_the_same_request(proj):
    from reveal import api
    with pytest.raises(RequestValidationError, match=r"control 'top' is not read by this answer \(stats_summary"):
        api.query('metrics://.', top=3)
    with pytest.raises(RequestValidationError, match=r"control 'limit' is not read by this answer \(stats_file"):
        api.query('metrics://app.py?limit=2')


@pytest.mark.parametrize('uri', [
    'metrics://.?hotspots&top=3&churn=on&tests=exclude&sort=lines&limit=2&offset=1&detail=summary&code-only'
    '&exclude=conf.yaml&lines>0',
    'metrics://.?view=hotspots&limit=2&offset=1&churn=on&tests=include&code-only&exclude=conf.yaml&lines>0',
    'metrics://.?sort=lines&limit=2&offset=1&detail=summary&code-only&exclude=conf.yaml&lines>0',
    'metrics://app.py?hotspots&top=1&churn=off&tests=exclude&sort=lines&detail=summary&lines>0',
    'metrics://app.py?view=hotspots&limit=1&offset=0&top=1',
    'metrics://.?view=provenance',
])
def test_metrics_answers_where_its_controls_are_read(proj, uri):
    run, doc = _run(uri)
    assert run.returncode == 0, (run.returncode, run.stderr)
    assert doc['type'] in ('stats_summary', 'stats_file', 'classify_report') and not _unread(doc), doc.get('meta')


def _data_unread(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'control_unread_by_data']


@pytest.mark.parametrize('uri', ['metrics://.?view=hotspots&since=2020-01-01&merges=off',
                                 'metrics://app.py?hotspots&since=2020-01-01&no_merges=true'])
def test_metrics_churn_bounds_outside_git_are_disclosed_by_the_data(proj, uri):
    """since and merges bound the churn walk, which a target with no git history does not have: only the data can
    say so, so the answer discloses them with the one shared warning (Scott 2026-11-18, Q2), exit 0, where the
    ledger's unused-input note stood."""
    run, doc = _run(uri)
    assert run.returncode == 0, run.stderr
    assert not _unread(doc), doc.get('meta')
    [warning] = _data_unread(doc)
    assert warning['fields'] == ['since', 'merges'] and 'no effect on this data' in warning['message'], warning


def test_metrics_churn_bounds_in_a_git_repository_are_read(proj):
    import subprocess
    for argv in (('init', '-q'), ('add', '.'),
                 ('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '-m', 'one')):
        subprocess.run(['git', *argv], cwd=proj, check=True, timeout=60, capture_output=True)
    run, doc = _run('metrics://.?view=hotspots&since=2020-01-01&merges=off')
    assert run.returncode == 0, run.stderr
    assert not _unread(doc) and not _data_unread(doc), doc.get('meta')


def test_metrics_legacy_top_still_caps_the_hotspot_view(proj):
    """``top`` in view=hotspots is the retired spelling of limit (BACK-2621): it answers, with its note."""
    run, doc = _run('metrics://.?view=hotspots&top=1')
    assert run.returncode == 0, run.stderr
    assert len(doc['hotspots']) == 1 and not _unread(doc), doc.get('meta')


# --- patches ------------------------------------------------------------------------------------------------------

_SCAN, _PRESSURE = 'patches_scan, default', 'testability_report, view, view=pressure'


@pytest.mark.parametrize('argv,control,answer', [
    (('patches://tests?min_patches=2',), "'where'", _SCAN),                # the legacy word is where's term (BACK-2625)
    (('patches://tests?min_categories=2',), "'where'", _SCAN),
    (('patches://tests?where=patches>=2',), "'where'", _SCAN),
    (('patches://tests?include_unresolved',), "'include_unresolved'", _SCAN),
    (('patches://tests?test-paths=tests',), "'test-paths'", _SCAN),
    (('patches://.?view=pressure&min=2',), "'min'", _PRESSURE),
    (('patches://.?view=pressure&target=app',), "'target'", _PRESSURE),
    (('patches://.?view=pressure&private',), "'private'", _PRESSURE),
    (('patches://.?view=pressure&suppress=false',), "'suppress'", _PRESSURE),
    (('patches', 'tests', '--min-patches', '2'), "'where'", _SCAN),          # the subcommand
])
def test_patches_refuses_a_control_its_answer_does_not_read(proj, argv, control, answer):
    _refused(argv, control, answer)


def test_patches_api_refuses_the_same_request(proj):
    from reveal import api
    with pytest.raises(RequestValidationError, match=r"control 'where' is not read by this answer \(patches_scan"):
        api.query('patches://tests?min_patches=2')
    # the grouping is the view now: a second, different view is a conflict, not an unread control (BACK-2625)
    with pytest.raises(ValueError, match=r"view: conflicting spellings"):
        api.query('patches://.?view=pressure&group=file')


def test_patches_api_keyword_reaches_the_same_check(proj):
    """A typed keyword binds through the declarations as the URI does (it went to get_structure(**kwargs) and was
    dropped in silence, tests/test_api_typed_keywords_back2656.py)."""
    from reveal import api
    with pytest.raises(RequestValidationError, match=r"control 'where' is not read by this answer"):
        api.query('patches://tests', min_patches=2)


@pytest.mark.parametrize('uri', [
    'patches://tests?view=file&limit=1&min=1&target=app&private&suppress=off',
    'patches://.?view=pressure&test-paths=tests&limit=1&where=patches>=1&where=categories>=1&include_unresolved',
])
def test_patches_answers_where_its_controls_are_read(proj, uri):
    run, doc = _run(uri)
    assert run.returncode == 0, (run.returncode, run.stderr)
    assert doc['type'] in ('patches_scan', 'testability_report') and not _unread(doc), doc.get('meta')


@pytest.mark.parametrize('form', [('patches://.?view=pressure',), ('patches', '.', '--view', 'pressure')])
def test_all_lifts_the_pressure_view_cap(proj, form):
    """view=pressure caps each hotspot list with limit (default 20): --all lifts it, as ?limit=0 does (it was noted
    unused, and the cap stayed)."""
    capped, _ = _run(*form)
    lifted, doc = _run(*form, '--all')
    uncapped, expected = _run('patches://.?view=pressure&limit=0')
    assert lifted.returncode == capped.returncode == uncapped.returncode == 0, lifted.stderr
    assert not _unread(doc), doc.get('meta')
    assert len(json.loads(capped.stdout)['patch_hotspots']) == 20
    assert len(doc['patch_hotspots']) == len(expected['patch_hotspots']) == _TARGETS


# --- a sibling noun on the same seam ------------------------------------------------------------------------------

def test_markdown_refuses_through_its_own_declaration(proj):
    """A sibling noun on the same seam (Markdown declares since group 2d)."""
    (proj / 'guide.md').write_text('# Guide\n\n[a](app.py)\n', encoding='utf-8')
    run, _doc = _run('markdown://.?view=links&limit=1')
    assert run.returncode == 2 and "control 'limit' is not read by this answer" in run.stderr, run.stderr
