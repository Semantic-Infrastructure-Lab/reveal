"""BACK-2146: a declared adapter may name its answer type once the path is known (``result_type_at``).

``result_type_for(params)`` reads query parameters only, so an adapter whose type depends on whether
the path is a file or a directory (metrics) could not declare one. The runner asks ``result_type_at``
after it has bound the resource, and the answer is qualified against that type.
"""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.surface import SurfaceAdapter

pytestmark = pytest.mark.component


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'proj').mkdir()
    (tmp_path / 'proj' / 'app.py').write_text('import os\n\n\ndef load(k):\n    return os.getenv(k)\n', encoding='utf-8')
    return tmp_path / 'proj'


@pytest.mark.parametrize('argv', [['surface', 'proj'], ['surface://proj']])
def test_the_runner_asks_for_the_type_with_the_bound_path_and_qualifies_against_it(project, monkeypatch, argv):
    asked = []

    def at(params, path):
        asked.append((type(params).__name__, path))
        return 'surface_elsewhere'

    monkeypatch.setattr(SurfaceAdapter, 'result_type_at', staticmethod(at), raising=False)
    result = run(*argv, '--format', 'json')
    assert asked == [('QueryParams', 'proj')]
    assert result.returncode != 0, 'a surface_scan answer is not the declared surface_elsewhere'
    assert json.loads(result.stdout)['type'] == 'surface_elsewhere'


@pytest.mark.parametrize('argv', [['surface', 'proj'], ['surface://proj']])
def test_an_adapter_without_the_hook_is_unchanged(project, argv):
    """Negative control: no hook, the declared RESULT_TYPE qualifies the answer as before."""
    assert not hasattr(SurfaceAdapter, 'result_type_at')
    result = run(*argv, '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['type'] == 'surface_scan'


def test_a_hook_on_one_adapter_leaves_a_sibling_alone(project, monkeypatch):
    monkeypatch.setattr(SurfaceAdapter, 'result_type_at', staticmethod(lambda params, path: 'surface_elsewhere'),
                        raising=False)
    result = run('deps', 'proj', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['type'] == 'deps_scan'
