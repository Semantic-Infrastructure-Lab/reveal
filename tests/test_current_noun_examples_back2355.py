"""Independent qualification of documented current nouns, not detector changes."""
import json
import shlex

import pytest

from reveal.cli.invocation import COMMANDS
from test_example_recipes_run import _named_fixture_skip, named_harness

pytestmark = pytest.mark.contract


@pytest.mark.parametrize('command', [
    'reveal calls src --callers validate_item',
    'reveal metrics src',
    'reveal patches src --view pressure --tests tests',
])
def test_current_noun_valid_fixture_is_not_skipped(command):
    assert shlex.split(command)[1] in COMMANDS
    assert _named_fixture_skip(shlex.split(command)) is None


@pytest.mark.parametrize('command', [
    'reveal imaginary src', 'reveal calls absent.py --callers main',
    'reveal metrics <repo>', 'reveal patches ssl://example.com',
    'reveal calls src > output.json', 'reveal dev adapter newadapter',
    'reveal scaffold analyzer newanalyzer', 'reveal offline download',
])
def test_unavailable_or_unsafe_examples_remain_skipped(command):
    assert _named_fixture_skip(shlex.split(command))


@pytest.mark.parametrize('noun,args,uri,expected_type', [
    ('calls', ('src', '--callers', 'validate_item'),
     'calls://src?callers=validate_item', 'calls_query'),
    ('metrics', ('src',), 'metrics://src', 'stats_summary'),
    ('patches', ('src', '--view', 'pressure', '--tests', 'tests'),
     'patches://src?view=pressure&tests=tests', 'testability_report'),
])
def test_current_noun_executes_like_uri(named_harness, noun, args, uri, expected_type):
    code, out, err, _ = named_harness.run_subcommand(noun, *args, '--format', 'json')
    uri_code, uri_out, uri_err, _ = named_harness.run_subcommand(uri, '--format', 'json')
    assert code == uri_code == 0, (out, err, uri_out, uri_err)
    result, sibling = json.loads(out), json.loads(uri_out)
    assert result['type'] == sibling['type'] == expected_type
    assert result == sibling
    if noun == 'calls':
        assert result['target'] == 'validate_item'
        assert result['total_callers'] > 0
    elif noun == 'metrics':
        assert result['summary']['total_files'] > 0
        assert result['summary']['total_functions'] > 0
    else:
        assert result['summary']['total_boundary_profiles'] > 0
