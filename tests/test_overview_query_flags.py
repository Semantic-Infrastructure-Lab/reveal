"""BACK-1377: the overview subcommand and the overview:// URI form must turn the same
CLI flags into the same adapter query.

Characterization tests inspect the shared typed handoff and established walk policy.
Expansion flags reach the adapter through existing named forwarding.
The differential (subcommand vs URI, real fixture tree) at the bottom is the guard that the
two entry points stay in agreement.
"""

import json
import subprocess
import sys
from argparse import Namespace
from unittest.mock import patch

import pytest

from reveal.cli.commands.overview import create_overview_parser, run_overview
from reveal.cli.routing.uri import _inject_exclude_flag


def _bound_request(*argv):
    """Observe the actual typed handoff, named expansion flags and walk policy."""
    from reveal.utils.exclusions import active_exclusions
    from reveal.utils.gitignore import respect_gitignore_param
    from reveal.utils.query_parser import peek_query_items
    from reveal.utils.results import ResultBuilder
    from reveal.adapters.overview import OverviewAdapter
    seen = {}
    def observe(self, all=False, verbose=False, **kwargs):
        seen.update(params=dict(peek_query_items(self.query_params)), all=all, verbose=verbose,
                    excludes=list(active_exclusions()[1]), respect_gitignore=respect_gitignore_param({}))
        return ResultBuilder.create('overview', '.', scope={
            'total_code_files': 0, 'languages': [], 'skipped_gitignore': 0,
            'skipped_no_analyzer': 0, 'skipped_dirs': 0}, data={
            'stats': {'summary': {key: 0 for key in ('total_files', 'total_lines', 'total_code_lines',
                'total_functions', 'total_classes', 'avg_complexity', 'avg_quality_score')},
                'files': [], 'hotspots': []},
            'complex_functions': [], 'git_log': [], 'architecture': {
                'fan_in': [], 'entrypoints': [], 'components': [], 'circular_count': 0,
                'unsupported_extensions': {}, 'metadata': {'files_failed_count': 0,
                    'files_failed': [], 'files_lost_count': 0, 'files_lost': [], 'extraction_diagnostics': {}}}})
    args = create_overview_parser().parse_args(['.', '--format', 'json', *argv])
    with patch.object(OverviewAdapter, 'get_structure', observe), \
            patch('reveal.config.RevealConfig.ignore_patterns', return_value=[]), \
            patch('reveal.utils.json_utils.attach_provenance', side_effect=lambda r: r):
        run_overview(args)
    return seen


def test_defaults():
    request = _bound_request()
    assert request['params'] == {}  # Declaration defaults are not submitted controls.
    assert request['respect_gitignore'] is True


@pytest.mark.parametrize('flag', ['--all', '--verbose'])
def test_all_and_verbose_lift_the_top_cap(flag):
    request = _bound_request(flag)
    assert request[flag[2:]] is True
    assert 'top' not in request['params']  # Expansion is named forwarding, not URI injection.


def test_top_is_honored_without_all():
    assert _bound_request('--top', '2')['params']['top'] == 2


def test_no_gitignore_reaches_the_adapter():
    assert _bound_request('--no-gitignore')['respect_gitignore'] is False


def test_exclude_preserves_flag_order_in_walk_scope():
    assert _bound_request('--exclude', 'dist/*', '--exclude', '*.min.js')['excludes'] == ['dist/*', '*.min.js']


def test_no_exclude_sends_no_exclude_key():
    assert 'exclude' not in _bound_request()['params']


def test_section_switches():
    q = _bound_request('--no-git', '--no-imports')['params']
    assert (q['no_git'], q['no_imports']) == (True, True)


@pytest.mark.parametrize('values', [['dist/*'], ['a', 'b/*', '*.min.js']])
def test_uri_form_and_subcommand_preserve_the_same_exclude_values(values):
    from reveal.utils.query_parser import split_exclude_param
    args = Namespace(exclude=values)
    with patch('reveal.utils.exclusions.set_active_exclusions'):
        uri = _inject_exclude_flag('overview://x?top=5', 'overview', args)
    assert split_exclude_param(uri.partition('exclude=')[2]) == values
    assert _bound_request(*[t for v in values for t in ('--exclude', v)])['excludes'] == values


# --- differential on a real tree: subcommand vs URI, the guard that they agree ---------

def _fixture(tmp_path):
    for i, (ext, src) in enumerate({'py': 'def f(): pass\n', 'go': 'package m\nfunc F(){}\n',
                                    'rb': 'def f; end\n'}.items(), 1):
        (tmp_path / f'pkg{i}').mkdir()
        (tmp_path / f'pkg{i}' / f'm{i}.{ext}').write_text(src, encoding='utf-8')
    (tmp_path / '.gitignore').write_text('ignored/\n', encoding='utf-8')
    (tmp_path / 'ignored').mkdir()
    (tmp_path / 'ignored' / 'z.py').write_text('x = 1\n', encoding='utf-8')
    return tmp_path


def _json(cmd, cwd):
    out = subprocess.run([sys.executable, '-m', 'reveal', *cmd], capture_output=True, text=True,
                         encoding='utf-8', cwd=cwd, check=False)
    data = json.loads(out.stdout)
    for volatile in ('meta', 'provenance', 'contract_version', 'type', 'source', 'source_type',
                     'generated_at', 'path'):
        data.pop(volatile, None)
    return data


@pytest.mark.parametrize('flags', [
    [], ['--no-gitignore'], ['--exclude', 'pkg1'], ['--exclude', 'pkg1', '--exclude', 'pkg2'],
    ['--all'], ['--verbose'],
])
def test_subcommand_and_uri_agree(tmp_path, flags):
    root = _fixture(tmp_path)
    sub = _json(['overview', '.', '--no-git', '--no-imports', '--format', 'json', *flags], root)
    uri = _json(['overview://.?no_git=true&no_imports=true', '--format', 'json', *flags], root)
    assert sub == uri


def test_text_census_sniffs_cpp_headers_like_the_json_scope(tmp_path, capsys):
    """BACK-1428: the text census labelled every .h as C (by extension) while
    the JSON scope, which content-sniffs .h, counted the same files as C++."""
    from reveal.adapters.overview import OverviewAdapter, _render_language_breakdown
    (tmp_path / 'widget.h').write_text('namespace ui {\nclass Widget {\npublic:\n  int w;\n};\n}\n', encoding='utf-8')
    (tmp_path / 'widget.cpp').write_text('#include "widget.h"\nint f() { return 1; }\n', encoding='utf-8')
    (tmp_path / 'plain.h').write_text('int plain(void);\n', encoding='utf-8')
    report = OverviewAdapter(str(tmp_path), 'no_git=true&no_imports=true').get_structure()
    scope = {row['language']: row['files'] for row in report['scope']['languages']}
    out = '\n'.join(_render_language_breakdown(report['stats']['files'], 5))
    assert scope == {'C++': 2, 'C': 1}
    assert 'C++                 2 files' in out
    assert 'C                   1 files' in out
