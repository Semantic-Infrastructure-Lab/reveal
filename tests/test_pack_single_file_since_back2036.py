"""Existing single-file Pack inputs retain scope when combined with Git --since."""
import json
import subprocess
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import pack

pytestmark = pytest.mark.component


def _git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True,
                          encoding='utf-8', timeout=15, check=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'real repo'
    root.mkdir()
    _git(root, 'init', '-q')
    for name in ('module.py', 'stable.py', 'other_changed.py'):
        (root / name).write_text(f'def {name.removesuffix(".py")}():\n    return 1\n', encoding='utf-8')
    _git(root, 'add', '.')
    _git(root, '-c', 'user.name=Reveal fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'first')
    (root / 'module.py').write_text('def selected_file_marker():\n    return 2\n', encoding='utf-8')
    (root / 'other_changed.py').write_text('def outside_scope_marker():\n    return 3\n', encoding='utf-8')
    _git(root, 'add', '.')
    _git(root, '-c', 'user.name=Reveal fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'second')
    return root


@pytest.mark.parametrize('filename', ['module.py', 'stable.py'])
def test_file_helper_discovers_parent_git_root_and_keeps_repository_changed_set(repo, filename):
    changed, error = pack._get_changed_files(repo / filename, 'HEAD~1')
    assert error is None
    assert changed == {str((repo / 'module.py').resolve()), str((repo / 'other_changed.py').resolve())}


@pytest.mark.parametrize('filename', ['module.py', 'stable.py'])
def test_adapter_keeps_exact_one_file_candidate_population_and_existing_content_tier(repo, filename):
    source = repo / filename
    baseline = pack.PackAdapter(str(source), 'budget=8000&content=true').get_structure()
    owner = pack.PackAdapter(str(source), 'budget=8000&content=true&since=HEAD~1')
    result = owner.get_structure()
    assert owner.since_error is None and result['source_type'] == 'file'
    assert result['path'] == baseline['path'] and result['meta']['total_candidates'] == result['meta']['selected'] == 1
    assert result['meta']['changed_files_count'] == 2 and result['meta']['since'] == 'HEAD~1'
    assert result['meta']['used_tokens_approx'] == baseline['meta']['used_tokens_approx']
    selected, = result['files']
    assert selected['path'] == source.as_posix() and selected['relative'] == '.'
    changed = filename == 'module.py'
    assert selected['changed'] is changed
    assert selected['priority'] == baseline['files'][0]['priority'] + (20 if changed else 0)
    content, = result['content']
    assert content['file'] == '.' and content['changed'] is changed
    if changed:
        assert content['content_type'] == 'full' and content['content'] == source.read_text(encoding='utf-8')
    else:
        assert content == baseline['content'][0]
    assert 'outside_scope_marker' not in json.dumps(result)


@pytest.mark.parametrize('spelling', ['command', 'uri'])
@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_public_file_since_uses_shared_helper_and_returns_legacy_success(repo, spelling, fmt):
    source = repo / 'module.py'
    args = (['pack', str(source), '--budget', '8000', '--since', 'HEAD~1', '--content'] if spelling == 'command' else
            ['pack://' + source.as_posix() + '?budget=8000&since=HEAD~1&content=true'])
    result = run(*args, '--format', fmt)
    assert result.returncode == 0, result.stderr
    if fmt == 'json':
        data = json.loads(result.stdout)
        assert data['files'][0]['relative'] == '.' and data['files'][0]['changed'] is True
        assert data['meta']['total_candidates'] == 1 and data['meta']['changed_files_count'] == 2
        assert data['content'][0]['content_type'] == 'full'
    else:
        assert 'selected_file_marker' in result.stdout
    assert 'outside_scope_marker' not in result.stdout


@pytest.mark.parametrize('tool', ['specialized', 'generic-text', 'generic-json'])
def test_decorated_tools_accept_existing_file_since_and_keep_other_changed_file_out(repo, tool):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_pack, reveal_query
    source = repo / 'module.py'
    if tool == 'specialized':
        result = reveal_pack(str(source), budget=8000, since='HEAD~1', content=True)
    else:
        result = reveal_query('pack://' + source.as_posix() + '?budget=8000&since=HEAD~1&content=true',
                              provenance=tool == 'generic-json')
    assert type(result) is str and 'selected_file_marker' in result
    assert 'outside_scope_marker' not in result
    if tool == 'generic-json':
        data = json.loads(result)
        assert data['meta']['total_candidates'] == 1 and data['files'][0]['changed'] is True
    else:
        assert 'Changed files:  2' in result


@pytest.mark.parametrize('consumer', ['helper', 'adapter', 'native-json', 'specialized', 'generic-json'])
def test_invalid_ref_remains_existing_nonfatal_fallback_without_new_json_error_contract(repo, consumer):
    source = repo / 'module.py'
    query = 'budget=8000&content=true&since=missing-ref-for-independent-fixture'
    if consumer == 'helper':
        changed, error = pack._get_changed_files(source, 'missing-ref-for-independent-fixture')
        assert changed == set() and error
        return
    if consumer == 'adapter':
        owner = pack.PackAdapter(str(source), query)
        result = owner.get_structure()
        assert owner.since_error
    elif consumer == 'native-json':
        response = run('pack', str(source), '--since', 'missing-ref-for-independent-fixture', '--format', 'json')
        assert response.returncode == 0 and 'Warning: --since:' in response.stderr
        result = json.loads(response.stdout)
    else:
        pytest.importorskip('mcp')
        from reveal.mcp_server import reveal_pack, reveal_query
        if consumer == 'specialized':
            answer = reveal_pack(str(source), since='missing-ref-for-independent-fixture')
            assert type(answer) is str and 'Warning: --since:' in answer
            return
        answer = reveal_query('pack://' + source.as_posix() + '?' + query, provenance=True)
        assert type(answer) is str
        assert 'Not a directory' not in answer, answer
        result = json.loads(answer.partition('\n[stderr:')[0])
    assert not result.get('error') and 'since_error' not in result and 'since_error' not in result['meta']
    assert result['meta']['changed_files_count'] == 0 and result['meta']['total_candidates'] == 1
    assert result['files'][0]['changed'] is False


def test_directory_and_no_since_file_controls_preserve_existing_scope(repo):
    changed, error = pack._get_changed_files(repo, 'HEAD~1')
    assert error is None and len(changed) == 2
    directory = pack.PackAdapter(str(repo), 'budget=8000&content=true&since=HEAD~1').get_structure()
    assert directory['meta']['total_candidates'] == 3 and sum(item['changed'] for item in directory['files']) == 2
    file = pack.PackAdapter(str(repo / 'module.py'), 'budget=8000&content=true').get_structure()
    assert file['meta']['total_candidates'] == 1 and not file['files'][0]['changed']


def test_non_git_directory_preserves_existing_error_tuple(tmp_path):
    changed, error = pack._get_changed_files(tmp_path, 'HEAD~1')
    assert changed == set() and error == 'not a git repository'


def test_option_like_ref_uses_read_only_git_boundary_without_writing_output(repo, tmp_path, monkeypatch):
    real_run = pack.subprocess.run
    calls = []
    def observed(command, *args, **kwargs):
        calls.append((command, kwargs))
        return real_run(command, *args, **kwargs)
    monkeypatch.setattr(pack.subprocess, 'run', observed)
    artifact = tmp_path / 'must-not-exist'
    changed, error = pack._get_changed_files(repo, '--output=' + str(artifact))
    assert changed == set() and error and not artifact.exists()
    assert calls[0][0] == ['git', 'rev-parse', '--show-toplevel']
    assert calls[0][1]['cwd'] == str(repo)
    assert calls[1][0][:6] == ['git', 'diff', '--name-only', '-z', '--end-of-options', '--output=' + str(artifact) + '...HEAD']
    assert calls[1][1]['cwd'] == str(repo) and calls[0][1]['timeout'] == calls[1][1]['timeout'] == 10


def test_existing_relative_directory_and_directory_symlink_git_discovery_are_unchanged(repo, tmp_path, monkeypatch):
    expected, error = pack._get_changed_files(repo, 'HEAD~1')
    assert error is None
    monkeypatch.chdir(repo)
    assert pack._get_changed_files(Path('.'), 'HEAD~1') == (expected, None)
    link = tmp_path / 'directory-link'
    try:
        link.symlink_to(repo, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f'directory symlinks unavailable: {error}')
    assert pack._get_changed_files(link, 'HEAD~1') == (expected, None)
