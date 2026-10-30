"""Two output defects from the help review (BACK-2282).

(a) ``depends://<dir> --format json`` printed the renderer's private routing field
    ``_format`` ("text") as if it were part of the answer. Only ``?format=dot`` needs it, and
    that request prints Graphviz, never JSON, so the field must not reach JSON at all.
(b) ``architecture <dir> --against REF`` wrote its header (and JSON ``path``) as the resolved
    absolute path whatever the user typed, and when the working tree was provably identical to
    REF it printed a ``0.0 -> 0.0`` complexity line instead of saying so.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct, _run_reveal_in

pytestmark = [pytest.mark.component]


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


PKG = {
    'pyproject.toml': '[project]\nname = "fx"\n',
    'pkg/__init__.py': '',
    'pkg/utils.py': 'def helper():\n    return 1\n',
    'pkg/models.py': 'from .utils import helper\n\nVALUE = helper()\n',
}


# ---- (a) depends:// _format ---------------------------------------------------------------

def test_depends_directory_json_has_no_private_format_field(tmp_path):
    root = _write(tmp_path / 'fx', PKG)
    result = _run_reveal_direct(f'depends://{(root / "pkg").as_posix()}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc['type'] == 'dependency_summary'
    assert '_format' not in doc
    # the answer itself is still there (control: the fix removed one key, not the summary)
    assert any(m['module'].endswith('utils.py') for m in doc['modules'])


def test_depends_file_json_never_had_the_field(tmp_path):
    """Negative control: the file-target branch never set _format; it stays absent."""
    root = _write(tmp_path / 'fx', PKG)
    result = _run_reveal_direct(f'depends://{(root / "pkg" / "utils.py").as_posix()}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert doc['type'] == 'module_dependents'
    assert '_format' not in doc


def test_depends_directory_text_is_still_the_summary(tmp_path):
    """Negative control: without ?format=dot the text render is the module summary."""
    root = _write(tmp_path / 'fx', PKG)
    result = _run_reveal_direct(f'depends://{(root / "pkg").as_posix()}')
    assert result.returncode == 0, result.stderr
    assert 'imported internally' in result.stdout
    assert 'digraph' not in result.stdout


def test_depends_format_dot_still_draws_graphviz(tmp_path):
    """?format=dot keeps its one job: Graphviz on stdout, also when --format json is given
    (as on imports:// and calls://, the URI override wins), so no JSON carries the field."""
    root = _write(tmp_path / 'fx', PKG)
    uri = f'depends://{(root / "pkg").as_posix()}?format=dot'
    for extra in ((), ('--format', 'json')):
        result = _run_reveal_direct(uri, *extra)
        assert result.returncode == 0, result.stderr
        assert result.stdout.lstrip().startswith('digraph depends'), (extra, result.stdout[:200])
        assert '_format' not in result.stdout


# ---- (b) architecture --against -------------------------------------------------------------

def _repo(root: Path) -> str:
    pygit2 = pytest.importorskip('pygit2')
    _write(root, PKG)
    repo = pygit2.init_repository(str(root))
    repo.index.add_all()
    repo.index.write()
    signature = pygit2.Signature('fixture', 'fixture@example.invalid')
    return str(repo.create_commit('HEAD', signature, signature, 'base', repo.index.write_tree(), []))


def test_against_header_and_path_are_spelled_as_typed(tmp_path):
    base = _repo(tmp_path / 'proj')
    result = _run_reveal_in(tmp_path, 'architecture', 'proj/pkg', '--against', base)
    assert result.returncode == 0, result.stderr
    assert 'Overview Diff: proj/pkg\n' in result.stdout
    assert tmp_path.resolve().as_posix() not in result.stdout

    doc = json.loads(_run_reveal_in(tmp_path, 'architecture', 'proj/pkg', '--against', base,
                                    '--format', 'json').stdout)
    assert doc['path'] == 'proj/pkg'
    assert doc['source'] == 'proj/pkg'


def test_against_absolute_target_stays_absolute(tmp_path):
    """Negative control: an absolute spelling is echoed as given (POSIX separators)."""
    base = _repo(tmp_path / 'proj')
    target = (tmp_path / 'proj' / 'pkg').resolve()
    doc = json.loads(_run_reveal_direct('architecture', str(target), '--against', base,
                                        '--format', 'json').stdout)
    assert doc['path'] == target.as_posix()


def test_against_identical_tree_says_so(tmp_path):
    base = _repo(tmp_path / 'proj')
    result = _run_reveal_in(tmp_path, 'architecture', 'proj/pkg', '--against', base)
    assert result.returncode == 0, result.stderr
    assert f'is identical to {base}' in result.stdout
    # nothing was measured, so no measured-looking zero line
    assert 'Complexity centroid' not in result.stdout
    doc = json.loads(_run_reveal_in(tmp_path, 'architecture', 'proj/pkg', '--against', base,
                                    '--format', 'json').stdout)
    assert doc['analysis']['basis'] == 'identical_tree'


def test_against_changed_tree_does_not_claim_identical(tmp_path):
    """Negative control: a dirty tree is analyzed and printed as before."""
    base = _repo(tmp_path / 'proj')
    with (tmp_path / 'proj' / 'pkg' / 'utils.py').open('a', encoding='utf-8') as stream:
        stream.write('\ndef extra():\n    return 2\n')
    result = _run_reveal_in(tmp_path, 'architecture', 'proj/pkg', '--against', base)
    assert result.returncode == 0, result.stderr
    assert 'is identical to' not in result.stdout
    assert 'Complexity centroid' in result.stdout
    assert 'Overview Diff: proj/pkg\n' in result.stdout
