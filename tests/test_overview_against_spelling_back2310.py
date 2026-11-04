"""BACK-2310: an ``overview --against`` error names the target as the user spelled it.

The repository lookup resolved the target first and put the resolved path in its error,
so ``reveal overview proj --against HEAD`` outside a repository printed the analyst's
absolute host path (BACK-1194/BACK-1366: answers echo the user's spelling).
"""
import json

import pytest

from conftest import _run_reveal_in


@pytest.fixture
def outside_repo(tmp_path):
    (tmp_path / 'proj').mkdir()
    (tmp_path / 'proj' / 'a.py').write_text('x = 1\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_not_a_repository_names_the_spelled_target(outside_repo, fmt):
    result = _run_reveal_in(outside_repo, 'overview', 'proj', '--against', 'HEAD', '--format', fmt)
    shown = result.stderr + result.stdout
    if 'Not a git repository' not in shown:
        pytest.skip('tmp_path sits inside a git repository on this host')  # failure path not reached
    assert str(outside_repo) not in shown
    assert str(outside_repo.resolve()) not in shown
    assert 'Not a git repository: proj' in shown
    if fmt == 'json':
        body = json.loads(result.stdout)
        assert body['error'] == 'Not a git repository: proj'
        assert body['source'] == 'proj'


@pytest.mark.parametrize('build', ['create', 'create_error', 'contract_fields'])
def test_envelope_source_uses_forward_slashes_for_a_windows_path(build):
    # BACK-2310 part 2: str(Path) is backslashed on Windows, so a nested relative target
    # reached the envelope as 'proj\\sub'. PureWindowsPath reproduces that on any OS.
    from pathlib import PureWindowsPath

    from reveal.utils.results import ResultBuilder, add_cli_contract_fields

    source = PureWindowsPath('proj/sub')
    assert str(source) == 'proj\\sub'  # positive control: the input really is backslashed
    if build == 'create':
        result = ResultBuilder.create('x', source, source_type='directory')
    elif build == 'create_error':
        result = ResultBuilder.create_error('x', source, 'boom', source_type='directory')
    else:
        result = add_cli_contract_fields({}, result_type='x', source=source)
    assert result['source'] == 'proj/sub'
