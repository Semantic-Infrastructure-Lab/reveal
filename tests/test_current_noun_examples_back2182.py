"""Named documentation coverage for current noun commands (BACK-2182)."""
import json
import shlex

import pytest

import test_example_recipes_run as recipes
from test_example_recipes_run import named_harness

pytestmark = pytest.mark.contract


def _current_nouns():
    return [p for p in recipes._named_fixture_commands()
            if shlex.split(p.values[0])[1] in {'calls', 'patches'}]


@pytest.mark.parametrize('documented', [pytest.param(p, id=p.id) for p in _current_nouns()])
def test_existing_current_noun_example_is_covered(documented):
    """Coverage RED: the real target exists, but the old gate mistakes the noun for a path."""
    assert not documented.marks, (documented.id, documented.marks)


def test_current_noun_and_uri_controls_use_existing_named_paths():
    for command in ('reveal metrics src --format json',
                    'reveal imports src --importers',
                    'reveal metrics://src --format=json'):
        assert recipes._named_fixture_skip(shlex.split(command)) is None


@pytest.mark.parametrize('command,reason', [
    ('reveal mystery src', 'names mystery'),
    ('reveal calls missing --callers validate_item', 'names missing'),
    ('reveal calls <path> --callers validate_item', '<placeholder>'),
    ('reveal calls src > output.txt', 'shell redirection'),
    ('reveal health ssl://example.com', 'live host'),
    ('reveal dev new-adapter demo', 'writes generated'),
    ('reveal scaffold adapter demo', 'writes generated'),
    ('reveal offline', 'download'),
    ('reveal patches src --view pressure --tests tests missing', 'names missing'),
    ('reveal calls src --callees missing.py:main', 'names missing.py'),
])
def test_unavailable_or_mutating_examples_stay_disclosed(command, reason):
    observed = recipes._named_fixture_skip(shlex.split(command))
    assert observed is not None and reason in observed


@pytest.mark.parametrize('documented', [pytest.param(p, id=p.id) for p in _current_nouns()])
def test_current_noun_examples_actually_execute(named_harness, documented):
    # Call the gate directly so a collector skip cannot hide a runtime/document defect.
    recipes._assert_text_as_written(named_harness, documented.values[0], literal=True)


def test_metrics_noun_and_uri_report_the_existing_fixture(named_harness):
    answers = []
    for name, args in [('metrics', ('src', '--format', 'json')),
                       ('metrics://src', ('--format', 'json'))]:
        code, out, err, _ = named_harness.run_subcommand(name, *args)
        assert code == 0 and not err
        payload = json.loads(out)
        assert payload['type'] == 'stats_summary'
        assert payload['summary']['total_files'] > 0
        assert any(row['file'] == 'validators.py' and row['elements']['functions'] > 0
                   for row in payload['files'])
        answers.append(payload)
    assert answers[0] == answers[1]


def test_current_nouns_analyze_real_calls_and_test_scope(named_harness):
    code, out, err, _ = named_harness.run_subcommand(
        'calls', 'src', '--callers', 'validate_item', '--format', 'json')
    calls = json.loads(out)
    assert code == 0 and not err and calls['total_callers'] > 0
    assert any(row['file'] == 'src/processor.py' and row['caller'] == 'process_batch'
               for row in calls['levels'][0]['callers'])
    code, out, err, _ = named_harness.run_subcommand(
        'patches', 'src', '--view', 'pressure', '--tests', 'tests', '--format', 'json')
    patches = json.loads(out)
    assert code == 0 and not err and patches['type'] == 'testability_report'
    assert patches['test_scope']['files_scanned'] == 1
    assert patches['summary']['total_boundary_profiles'] > 0
    # The existing named test has no patches; this is coverage, not fabricated pressure.
    assert patches['summary']['total_patch_uses'] == 0


@pytest.mark.parametrize('command', [
    'reveal patches src --view pressure --tests tests integration_tests --top 20',
    'reveal patches tests --target package.* --group target --limit 5',
    'reveal calls src --callees src/app.py:main --depth 2',
    'reveal calls src --callees Foo::run',
    'reveal calls src --callers validate_item --depth 2',
])
def test_secondary_path_checks_preserve_scalar_and_qualified_name_controls(command):
    assert recipes._named_fixture_skip(shlex.split(command)) is None
