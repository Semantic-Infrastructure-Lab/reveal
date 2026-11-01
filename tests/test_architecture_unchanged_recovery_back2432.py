"""A file whose syntax does not fully parse blocks a comparison only when it can bias it (BACK-2432).

`overview --against` used to exit 3 on any repository holding one file tree-sitter recovers from,
even when that file is byte-identical at both refs. Such a file is now removed from the complexity
population on both sides and the answer says so; a recovered file that differs between the refs,
exists on one side only, or cannot be fully listed still makes the comparison unavailable.
"""

import json

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct  # noqa: E402

BROKEN_SHELL = 'f() {\n  echo ok\n}\ng() {\n  case x in\n'


def _branchy(name, branches):
    body = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(branches))
    return f'def {name}(x):\n{body}    return -1\n'


def write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


def make_repo(root, *, broken=('broken.sh',)):
    repo = pygit2.init_repository(str(root))
    write(root / 'stable.py', _branchy('heavy', 12))
    write(root / 'app.py', _branchy('grow', 10))
    for name in broken:
        write(root / name, BROKEN_SHELL)
    repo.index.add_all()
    repo.index.write()
    signature = pygit2.Signature('fixture', 'fixture@example.invalid')
    base = str(repo.create_commit('HEAD', signature, signature, 'base', repo.index.write_tree(), []))
    write(root / 'app.py', _branchy('grow', 16))  # a real complexity change in the live head
    return base


def compare(root, base, *extra):
    response = _run_reveal_direct('overview', str(root), '--against', base, '--format', 'json', *extra)
    return response, json.loads(response.stdout)


def _warning_types(result):
    return [warning.get('type') for warning in result['meta'].get('warnings', [])]


def test_unchanged_recovered_file_is_excluded_and_comparison_completes(tmp_path):
    base = make_repo(tmp_path)
    response, result = compare(tmp_path, base)
    assert response.returncode == 0, response.stdout
    assert result['analysis']['complete'] is True
    assert result['analysis']['complexity_excluded'] == ['broken.sh']
    assert result['deltas'] is not None and 'error' not in result
    assert result['deltas']['complexity_centroid']['change'] != 0
    assert 'parse_recovered' not in _warning_types(result)
    excluded = [w for w in result['meta']['warnings'] if w.get('type') == 'complexity_population_excluded']
    assert len(excluded) == 1 and excluded[0]['files'] == ['broken.sh']
    assert 'identical at both refs' in excluded[0]['message']


def test_line_ending_only_difference_still_counts_as_unchanged(tmp_path):
    """A Windows checkout with core.autocrlf stores LF in the commit and CRLF in the working tree:
    the same file, so the exclusion must hold (the Windows CI shard failed on it)."""
    base = make_repo(tmp_path)
    (tmp_path / 'broken.sh').write_bytes(BROKEN_SHELL.replace('\n', '\r\n').encode('utf-8'))
    response, result = compare(tmp_path, base)
    assert response.returncode == 0, response.stdout
    assert result['analysis']['complete'] is True
    assert result['analysis']['complexity_excluded'] == ['broken.sh']


def test_changed_content_is_not_masked_by_line_ending_normalisation(tmp_path):
    base = make_repo(tmp_path)
    changed = BROKEN_SHELL.replace('echo ok', 'echo changed').replace('\n', '\r\n')
    (tmp_path / 'broken.sh').write_bytes(changed.encode('utf-8'))
    response, _ = compare(tmp_path, base)
    assert response.returncode == 3


def test_exclusion_answer_equals_explicit_exclude(tmp_path):
    base = make_repo(tmp_path)
    _, implicit = compare(tmp_path, base)
    control_response, control = compare(tmp_path, base, '--exclude', 'broken.sh')
    assert control_response.returncode == 0 and control['analysis']['complete'] is True
    assert implicit['deltas'] == control['deltas']


def test_recovered_file_changed_between_refs_still_blocks(tmp_path):
    base = make_repo(tmp_path)
    with (tmp_path / 'broken.sh').open('a', encoding='utf-8') as stream:
        stream.write('  y) echo y ;;\n')
    response, result = compare(tmp_path, base)
    assert response.returncode == 3
    assert result['deltas'] is None and result['analysis']['complete'] is False
    assert 'complexity_excluded' not in result['analysis']
    assert 'broken.sh' in result['error'] and '--exclude' in result['error']


def test_recovered_file_on_head_only_still_blocks(tmp_path):
    base = make_repo(tmp_path, broken=())
    write(tmp_path / 'new_broken.sh', BROKEN_SHELL)
    response, result = compare(tmp_path, base)
    assert response.returncode == 3
    assert result['deltas'] is None and 'new_broken.sh' in result['error']


def test_unlisted_recovered_files_cannot_be_verified_and_block(tmp_path):
    # The shared warning lists at most five files; a sixth cannot be checked, so nothing is excluded.
    base = make_repo(tmp_path, broken=tuple(f'broken{i}.sh' for i in range(6)))
    response, result = compare(tmp_path, base)
    assert response.returncode == 3
    assert result['deltas'] is None and 'complexity_excluded' not in result['analysis']
    assert 'parse_recovered' in _warning_types(result)


def test_text_output_states_the_exclusion_and_shows_deltas(tmp_path):
    base = make_repo(tmp_path)
    response = _run_reveal_direct('overview', str(tmp_path), '--against', base)
    assert response.returncode == 0
    assert 'unavailable' not in response.stdout
    assert 'Complexity centroid' in response.stdout
    assert 'broken.sh' in response.stdout + response.stderr
