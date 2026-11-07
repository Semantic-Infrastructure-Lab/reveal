"""A request rejected as invalid (exit 2) prints its error only, not an empty answer (BACK-2538).

The error line and exit 2 were right (rule 9, BACK-2161), but the text renderer then printed the zero
answer: `calls ?callers=nosuch` printed 'Callers of: nosuch ... Total: 0', and `imports
?importers=nosuch.py` printed 'No module under this path has an importer', which reads as a second,
contradictory answer. JSON keeps its error envelope.
"""
import json

import pytest

from conftest import _run_reveal_direct


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'pyproject.toml').write_text('[project]\nname = "proj"\n', encoding='utf-8')
    (root / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (root / 'pkg' / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (root / 'pkg' / 'b.py').write_text('from pkg.a import f\n\ndef g():\n    return f()\n', encoding='utf-8')
    return root


REJECTED = [
    (['calls://proj/pkg?callers=nosuch'], 'Callers of'),
    (['calls', 'proj/pkg', '--callers', 'nosuch'], 'Callers of'),
    (['imports://proj/pkg?importers=nosuch.py'], 'No module under this path has an importer'),
    (['imports', 'proj/pkg', '--importers', 'nosuch.py'], 'No module under this path has an importer'),
]


@pytest.mark.parametrize('argv,body', REJECTED)
def test_text_rejection_prints_the_error_and_no_answer_body(project, argv, body):
    result = _run_reveal_direct(*argv, '--no-gitignore')
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert 'nosuch' in result.stderr
    assert body not in result.stdout, result.stdout
    assert 'Total:' not in result.stdout and 'Modules with importers' not in result.stdout, result.stdout
    if argv[0].startswith('calls'):
        # The caveats stay: a tree hidden by .gitignore can be why a name is absent (BACK-2247).
        assert 'Dynamic dispatch' in result.stdout, result.stdout


@pytest.mark.parametrize('argv,body', REJECTED)
def test_json_rejection_keeps_its_error_envelope(project, argv, body):
    result = _run_reveal_direct(*argv, '--no-gitignore', '--format', 'json')
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert 'nosuch' in json.loads(result.stdout)['error']


def test_a_target_that_exists_still_renders_its_answer(project):
    """Positive control: a real target with a real answer still prints its body."""
    result = _run_reveal_direct('calls://proj/pkg?callers=f', '--no-gitignore')
    assert result.returncode == 0, result.stderr
    assert 'Callers of' in result.stdout and 'g' in result.stdout
