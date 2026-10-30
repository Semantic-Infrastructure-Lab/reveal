"""Both overview spellings bind controls through the declared parameter owner."""
from functools import partial
from unittest.mock import patch

import pytest

from reveal.adapters.overview import OverviewAdapter
from reveal.cli.routing.declared import create_declared_parser, run_declared_command
from reveal.utils.exclusions import active_exclusions
from reveal.utils.gitignore import respect_gitignore_param
from reveal.utils.query_parser import peek_query_items

create_overview_parser = partial(create_declared_parser, 'overview')
run_overview = partial(run_declared_command, 'overview')


def bound_request(tmp_path, *argv):
    seen = {}
    original = OverviewAdapter.get_structure
    def observe(self, **kwargs):
        seen.update(params=dict(peek_query_items(self.query_params)), kwargs=kwargs,
                    excludes=list(active_exclusions()[1]), respect=respect_gitignore_param({}))
        return original(self, **kwargs)
    args = create_overview_parser().parse_args([str(tmp_path), '--format', 'json', *argv])
    with patch.object(OverviewAdapter, 'get_structure', observe), \
            patch('reveal.config.RevealConfig.ignore_patterns', return_value=[]):
        run_overview(args)
    return seen


def test_defaults_are_not_submitted_controls(tmp_path):
    request = bound_request(tmp_path)
    assert request['params'] == {} and request['kwargs'] == {}


@pytest.mark.parametrize('flag', ['--all', '--verbose'])
def test_expansion_is_a_declared_control(tmp_path, flag):
    request = bound_request(tmp_path, flag)
    assert request['params'][flag[2:]] is True
    assert request['kwargs'] == {}


def test_top_zero_and_scope_only_are_bound(tmp_path):
    params = bound_request(tmp_path, '--top', '0', '--no-imports')['params']
    assert params == {'top': 0, 'no_imports': True}


def test_no_gitignore_and_exclude_keep_existing_walk_scope(tmp_path):
    request = bound_request(tmp_path, '--no-gitignore', '--exclude', 'dist/*', '--exclude', '*.min.js')
    assert request['respect'] is False
    assert request['excludes'] == ['dist/*', '*.min.js']
