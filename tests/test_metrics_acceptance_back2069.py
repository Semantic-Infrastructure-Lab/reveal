"""BACK-2069 acceptance: what metrics must keep when it absorbs stats, file hotspots and classify.

Pinned on one small fixture through each spelling that answers the question, so a rename or a
merge that quietly drops a field fails here (Phase 3 plan, step 5; preflight section 4):

- classify's full population (every analyzable file, not a ranked subset), its per-file tags,
  the vendor-banner and locale-fanout heuristics with the i18n-directory exemption,
  ``summary.total``, ``by_provenance``, ``excluded`` and ``excluded_by_extension``, answered
  without the rule pass;
- the file-local issue count (``quality.local_check_issues``) and its printed rule set
  (``meta.issue_count`` and the text footer, BACK-1884);
- the file hotspot ranking, which the ``hotspots`` noun's file section reads from the same owner.

``metrics://`` is the new spelling of all three (D2); ``stats://`` and ``classify://`` are retired
spellings that answer the same and print a replaced-by note until the cut (D5).
"""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.stats.issue_count import COUNTING_RULE, COUNT_FIELD, issue_count_line
from reveal.rules import RuleRegistry

pytestmark = pytest.mark.component

TANGLED = 'def tangled(x):\n' + ''.join(
    f'    if x == {n}:\n        x += {n}\n' for n in range(14)) + '    return x\n'

# Every file the fixture writes, with the tag classify gives it.
EXPECTED_TAGS = {
    'src/app.py': 'first_party',
    'src/tangled.py': 'first_party',
    'tests/test_app.py': 'test',
    'vendor/thirdparty.py': 'vendor',
    'assets/bundle.min.js': 'minified',
    # In-tree vendoring by banner (BACK-1238): no vendor/ directory, a /*! ... vN */ banner.
    'lib/js/moment.js': 'vendor',
    # Locale fan-out (BACK-1238): five language-code siblings outside an i18n directory.
    **{f'static/i18nbundle/{code}.js': 'vendor' for code in ('en', 'fr', 'de', 'es', 'it')},
    # The same fan-out under config/locales is the project's own translations (BACK-1242/1258).
    **{f'config/locales/{code}.yml': 'first_party' for code in ('en', 'fr', 'de', 'es', 'it')},
}
EXCLUDED_EXTENSION = '.unrecognized_back2069'


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _project(root):
    _write(root / 'src' / 'app.py',
           'def add(a, b):\n    return a + b\n\n\ndef risky(x):\n    try:\n        return 1 / x\n'
           '    except:\n        pass\n')  # one bare except: B001, a file-local rule
    _write(root / 'src' / 'tangled.py', TANGLED)  # average complexity 15: a file hotspot
    _write(root / 'tests' / 'test_app.py', 'from src.app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n')
    _write(root / 'vendor' / 'thirdparty.py', 'def third():\n    return 3\n')
    _write(root / 'assets' / 'bundle.min.js', 'var a=1;\n')
    _write(root / 'lib' / 'js' / 'moment.js', '/*! moment.js v2.29.4 */\n(function (g) {\n})();\n')
    for code in ('en', 'fr', 'de', 'es', 'it'):
        _write(root / 'static' / 'i18nbundle' / f'{code}.js', 'var x = 1;\n')
        _write(root / 'config' / 'locales' / f'{code}.yml', 'k: v\n')
    _write(root / f'notes{EXCLUDED_EXTENSION}', 'no analyzer reads this\n')
    return root


@pytest.fixture
def project(tmp_path):
    return _project(tmp_path / 'proj')


# The spellings that answer each question. Each is a function of the project directory.
PROVENANCE_SPELLINGS = {
    'metrics://?view=provenance': lambda d: [f'metrics://{d}?view=provenance'],
    'classify://': lambda d: [f'classify://{d}'],
}
METRICS_SPELLINGS = {
    'metrics://': lambda d: [f'metrics://{d}'],
    'stats://': lambda d: [f'stats://{d}'],
}
HOTSPOT_SPELLINGS = {
    'metrics://?hotspots=true': lambda d: [f'metrics://{d}?hotspots=true'],
    'metrics:// --hotspots': lambda d: [f'metrics://{d}', '--hotspots'],
    'stats://?hotspots=true': lambda d: [f'stats://{d}?hotspots=true'],
    'stats:// --hotspots': lambda d: [f'stats://{d}', '--hotspots'],
}
# Each retired spelling, the note it prints, and the new spelling whose answer it must equal.
RETIRED = {
    'stats://': ('stats://', 'metrics://<path> (the same answer)',
                 lambda d: [f'stats://{d}?hotspots=true'], lambda d: [f'metrics://{d}?hotspots=true']),
    'classify://': ('classify://', 'metrics://<path>?view=provenance (the same answer)',
                    lambda d: [f'classify://{d}'], lambda d: [f'metrics://{d}?view=provenance']),
}


def _json(argv):
    result = run(*argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def rule_pass(monkeypatch):
    """Count the rule pass: every RuleRegistry.check_file call, then the real one."""
    calls = []
    real = RuleRegistry.check_file.__func__

    def counted(cls, *args, **kwargs):
        calls.append(args[0] if args else kwargs.get('file_path'))
        return real(cls, *args, **kwargs)

    monkeypatch.setattr(RuleRegistry, 'check_file', classmethod(counted))
    return calls


@pytest.mark.parametrize('spelling', PROVENANCE_SPELLINGS)
def test_provenance_keeps_the_full_population_tags_and_exclusions(project, spelling, rule_pass):
    doc = _json(PROVENANCE_SPELLINGS[spelling](project))

    tags = {row['file']: row['provenance'] for row in doc['files']}
    assert tags == EXPECTED_TAGS
    assert len(doc['files']) == len(EXPECTED_TAGS), 'one row per file, no duplicates'
    summary = doc['summary']
    assert summary['total'] == len(EXPECTED_TAGS)
    assert summary['by_provenance'] == {'first_party': 7, 'vendor': 7, 'test': 1, 'minified': 1}
    assert summary['excluded'] == 1
    assert summary['excluded_by_extension'] == {EXCLUDED_EXTENSION: 1}
    # Classification reads paths and at most a few header lines: no rule runs, no issue count.
    assert rule_pass == []
    assert 'issue_count' not in (doc.get('meta') or {})


@pytest.mark.parametrize('spelling', PROVENANCE_SPELLINGS)
def test_provenance_population_is_the_metrics_population(project, spelling):
    """Positive control on "full population": the classified files are exactly the files metrics
    analyzes, so the tags cover the whole analyzed tree and not a ranked subset."""
    tagged = {row['file'] for row in _json(PROVENANCE_SPELLINGS[spelling](project))['files']}
    for metrics in METRICS_SPELLINGS.values():
        analyzed = {row['file'] for row in _json(metrics(project))['files']}
        assert tagged == analyzed == set(EXPECTED_TAGS)


@pytest.mark.parametrize('spelling', PROVENANCE_SPELLINGS)
def test_provenance_text_states_the_counts_and_the_exclusions(project, spelling):
    result = run(*PROVENANCE_SPELLINGS[spelling](project))
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert f'{len(EXPECTED_TAGS)} files' in out
    for label, count in (('first_party', 7), ('vendor', 7), ('test', 1), ('minified', 1)):
        assert f'  {label}: {count}' in out
    assert f'1 more file(s) not classified — no analyzer for: {EXCLUDED_EXTENSION} (1)' in out
    for path, tag in EXPECTED_TAGS.items():
        assert f'{tag:>11}  {path}' in out


@pytest.mark.parametrize('spelling', METRICS_SPELLINGS)
def test_metrics_keeps_the_file_local_issue_count_and_names_its_rule_set(project, spelling, rule_pass):
    doc = _json(METRICS_SPELLINGS[spelling](project))
    rows = {row['file']: row['quality'] for row in doc['files']}
    # The bare except (B001) and the complexity-15 function (C901) are file-local findings.
    assert {f: q[COUNT_FIELD] for f, q in rows.items() if q[COUNT_FIELD]} == {'src/app.py': 1, 'src/tangled.py': 1}
    assert rule_pass, 'positive control: the issue count runs the rule pass'

    basis = doc['meta']['issue_count']
    assert basis['rule'] == COUNTING_RULE and basis['field'] == COUNT_FIELD
    assert basis['rule_count'] == len(basis['rules'])
    assert 'B001' in basis['rules'] and 'I002' not in basis['rules'], 'file-local rules only'

    text = run(*METRICS_SPELLINGS[spelling](project))
    assert text.returncode == 0, text.stderr
    assert issue_count_line(doc) in text.stdout
    assert f"set {basis['rule_set_id']}" in text.stdout


@pytest.mark.parametrize('spelling', HOTSPOT_SPELLINGS)
def test_file_hotspots_rank_the_same_files_the_hotspots_noun_shows(project, spelling):
    ranked = _json(HOTSPOT_SPELLINGS[spelling](project))['hotspots']
    assert [(h['file'], h['hotspot_score']) for h in ranked] == [('src/tangled.py', 5.0)]
    assert ranked[0]['issues'] == ['Avg complexity: 15.0']

    noun = _json(['hotspots', str(project)])
    assert [(h['file'], h['hotspot_score'], h['quality_score']) for h in noun['file_hotspots']] == [
        (h['file'], h['hotspot_score'], h['quality_score']) for h in ranked]
    assert noun['meta']['issue_count']['rule'] == COUNTING_RULE


def _answer(doc):
    """The answer without the retirement fact and without the echoed source spelling."""
    doc = dict(doc)
    doc.pop('source', None)
    meta = dict(doc.get('meta') or {})
    warnings = [w for w in meta.get('warnings', []) if w.get('code') != 'retired_spelling']
    if warnings:
        meta['warnings'] = warnings
    else:
        meta.pop('warnings', None)
    if meta:
        doc['meta'] = meta
    else:
        doc.pop('meta', None)
    if isinstance(doc.get('files'), list):
        doc['files'] = sorted(doc['files'], key=lambda row: row['file'])
    return doc


@pytest.mark.parametrize('retired', RETIRED)
def test_a_retired_spelling_prints_its_replacement_and_answers_like_metrics(project, retired):
    old, replacement, old_argv, new_argv = RETIRED[retired]
    note = f'note: {old} is deprecated; use {replacement}.'

    as_old = run(*old_argv(project), '--format', 'json')
    as_new = run(*new_argv(project), '--format', 'json')
    assert as_old.returncode == as_new.returncode == 0, as_old.stderr + as_new.stderr
    assert as_old.stderr.count(note) == 1
    assert 'deprecated' not in as_new.stderr, 'the new spelling prints no note'

    old_doc, new_doc = json.loads(as_old.stdout), json.loads(as_new.stdout)
    retirement = [w for w in old_doc['meta']['warnings'] if w.get('code') == 'retired_spelling']
    assert [(w['old'], w['replacement'], w['stage']) for w in retirement] == [(old, replacement, 'note')]
    assert _answer(old_doc) == _answer(new_doc)

    text = run(*old_argv(project))
    assert text.returncode == 0 and text.stderr.count(note) == 1


def test_the_hotspots_noun_prints_no_retirement_note(project):
    """Negative control on a sibling: the hotspots noun composes metrics in-process and is not
    a retired spelling, so it says nothing about stats://."""
    result = run('hotspots', str(project), '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert 'deprecated' not in result.stderr
    assert not [w for w in json.loads(result.stdout).get('meta', {}).get('warnings', [])
                if w.get('code') == 'retired_spelling']


def test_an_unknown_metrics_view_is_rejected(project):
    result = run(f'metrics://{project}?view=everything', '--format', 'json')
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert 'provenance' in result.stdout + result.stderr
