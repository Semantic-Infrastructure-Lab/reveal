"""BACK-1377: the overview subcommand and the overview:// URI form must turn the same
CLI flags into the same adapter query.

Characterization tests: they pin what `run_overview` hands to `OverviewAdapter` so the
flag-injection logic can be shared with cli/routing/uri.py without changing behavior.
The differential (subcommand vs URI, real fixture tree) at the bottom is the guard that the
two entry points stay in agreement.
"""

import json
import subprocess
import sys
from argparse import Namespace
from unittest.mock import patch

import pytest

from reveal.adapters.overview import UNLIMITED_TOP
from reveal.cli.commands.overview import create_overview_parser, run_overview
from reveal.cli.routing.uri import _inject_exclude_flag


def _query_sent(*argv):
    """Parse `reveal overview <argv>` and return {key: value} of the adapter query."""
    args = create_overview_parser().parse_args(['.', '--format', 'json', *argv])
    with patch('reveal.cli.commands.overview.OverviewAdapter') as adapter, \
            patch('reveal.cli.commands.overview.OverviewRenderer'), \
            patch('reveal.utils.json_utils.attach_provenance', side_effect=lambda r: r):
        adapter.return_value.get_structure.return_value = {'type': 'overview'}
        run_overview(args)
    _path, query = adapter.call_args.args
    return dict(pair.partition('=')[::2] for pair in query.split('&'))


def test_defaults():
    # respect_gitignore is only sent when it is turned off (the adapter's default is on), the
    # same as the overview:// form -- the subcommand used to send respect_gitignore=true.
    assert _query_sent() == {'top': '5', 'no_git': 'false', 'no_imports': 'false'}


@pytest.mark.parametrize('flag', ['--all', '--verbose'])
def test_all_and_verbose_lift_the_top_cap(flag):
    assert _query_sent(flag)['top'] == str(UNLIMITED_TOP)


def test_top_is_honored_without_all():
    assert _query_sent('--top', '2')['top'] == '2'


def test_no_gitignore_reaches_the_adapter():
    assert _query_sent('--no-gitignore')['respect_gitignore'] == 'false'


def test_exclude_is_comma_joined_in_flag_order():
    assert _query_sent('--exclude', 'dist/*', '--exclude', '*.min.js')['exclude'] == 'dist/*,*.min.js'


def test_no_exclude_sends_no_exclude_key():
    assert 'exclude' not in _query_sent()


def test_section_switches():
    q = _query_sent('--no-git', '--no-imports')
    assert (q['no_git'], q['no_imports']) == ('true', 'true')


@pytest.mark.parametrize('values', [['dist/*'], ['a', 'b/*', '*.min.js']])
def test_uri_form_and_subcommand_share_the_exclude_format(values):
    """overview://X --exclude ... and `overview X --exclude ...` must send the same value."""
    args = Namespace(exclude=values)
    with patch('reveal.utils.exclusions.set_active_exclusions'):
        uri = _inject_exclude_flag('overview://x?top=5', 'overview', args)
    assert uri.partition('exclude=')[2] == _query_sent(*[t for v in values for t in ('--exclude', v)])['exclude']


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
