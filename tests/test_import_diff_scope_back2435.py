"""Identical recovered input can resolve differently at two refs (BACK-2435).

These are real partial-parse and resolver-input controls, not an enumeration of
unknown hidden imports. No comparison completeness policy is relaxed.
"""
import json
from pathlib import Path

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct  # noqa: E402
from reveal.diff import architecture_diff as diff  # noqa: E402

pytestmark = pytest.mark.component

PARTIAL = 'import { value } from "./target";\nexport const result = value;\nconst = ;;; }{\n'
HEALTHY = 'import { value } from "./target";\nexport const result = value;\n'


def _write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _repo(root, source):
    repo = pygit2.init_repository(str(root))
    _write(root, 'package.json', '{"name":"project"}\n')
    _write(root, 'app.ts', source)
    _write(root, 'target.ts', 'export const value = 1;\n')
    _write(root, 'stable.ts', 'export const stable = 2;\n')
    repo.index.add_all()
    repo.index.write()
    sig = pygit2.Signature('fixture', 'fixture@example.invalid')
    base = str(repo.create_commit('HEAD', sig, sig, 'base', repo.index.write_tree(), []))
    return repo, base


def _move_target(root):
    (root / 'target.ts').unlink()
    _write(root, 'target/index.ts', 'export const value = 1;\n')


def _fan_in(snapshot):
    root = snapshot['root']
    return {Path(row['file']).relative_to(root).as_posix(): row['fan_in']
            for row in snapshot['fan_in_out']}


def test_identical_partial_file_has_different_recovered_target_edges(tmp_path):
    _, base = _repo(tmp_path, PARTIAL)
    original = (tmp_path / 'app.ts').read_bytes()
    before = diff._snapshot(tmp_path, 5)
    _move_target(tmp_path)
    after = diff._snapshot(tmp_path, 5)
    assert (tmp_path / 'app.ts').read_bytes() == original
    assert before['completeness']['imports'] == after['completeness']['imports'] == 'incomplete'
    assert _fan_in(before)['target.ts'] == 1
    assert _fan_in(after)['target/index.ts'] == 1
    assert _fan_in(before)['stable.ts'] == _fan_in(after)['stable.ts'] == 0
    response = _run_reveal_direct('overview', str(tmp_path), '--against', base, '--format', 'json')
    result = json.loads(response.stdout)
    assert response.returncode == 3
    assert result['analysis']['complete'] is False
    assert result['deltas'] is None
    assert {w['snapshot'] for w in result['meta']['warnings']
            if w['type'] == 'partial_parse' and w['component'] == 'imports'
            and w['files'] == ['app.ts']} == {'base', 'head'}


def test_healthy_sibling_reports_the_resolution_delta(tmp_path):
    _, base = _repo(tmp_path, HEALTHY)
    _move_target(tmp_path)
    response = _run_reveal_direct('overview', str(tmp_path), '--against', base, '--format', 'json')
    result = json.loads(response.stdout)
    assert response.returncode == 0, result
    assert result['analysis']['complete'] is True
    assert result['deltas']['fan_in'] == [
        {'file': 'target.ts', 'base': 1, 'head': None, 'change': None},
        {'file': 'target/index.ts', 'base': None, 'head': 1, 'change': None},
    ]
    assert all(row['file'] != 'stable.ts' for row in result['deltas']['fan_in'])


def test_identical_partial_input_with_neutral_edit_still_discloses_loss(tmp_path):
    _, base = _repo(tmp_path, PARTIAL)
    _write(tmp_path, 'stable.ts', '// neutral edit\nexport const stable = 2;\n')
    response = _run_reveal_direct('overview', str(tmp_path), '--against', base, '--format', 'json')
    result = json.loads(response.stdout)
    assert response.returncode == 3
    assert result['analysis']['complete'] is False
    assert result['deltas'] is None
