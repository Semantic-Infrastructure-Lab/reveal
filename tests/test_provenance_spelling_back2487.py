"""BACK-2487: function provenance and hotspot paths must not depend on how the target is spelled.

Results echo the user's spelling (BACK-1366), so a scan of ``tests/proj`` reports
``tests/proj/vendor/lib.py``. The display helper joined that under the base again, so
the target's own ``tests/`` component reached provenance and every function was tagged
``test``; hotspots also showed ``tests/proj/...`` for functions beside ``vendor/...``
for files. A relative and an absolute spelling of one target must give one answer.
"""
import json

import pytest

from conftest import _run_reveal_in

_BRANCHY = "def {name}(x):\n" + "".join(
    f"    {'if' if i == 1 else 'elif'} x == {i}: return {i}\n" for i in range(1, 14)
) + "    return 0\n"

_EXPECTED = {'mainline': None, 'vendored': 'vendor', 'test_thing': 'test'}


@pytest.fixture
def nested_target(tmp_path):
    """A project whose own path contains a provenance component (``tests/``)."""
    root = tmp_path / 'tests' / 'proj'
    for sub, name in (('app/core.py', 'mainline'), ('vendor/lib.py', 'vendored'),
                      ('tests/test_lib.py', 'test_thing')):
        f = root / sub
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(_BRANCHY.format(name=name), encoding='utf-8')
    return tmp_path, root


def _json(result):
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('spelling', ['relative', 'dot-relative', 'absolute'])
def test_ast_provenance_is_spelling_independent(nested_target, spelling):
    cwd, root = nested_target
    target = {'relative': 'tests/proj', 'dot-relative': './tests/proj', 'absolute': str(root)}[spelling]
    data = _json(_run_reveal_in(cwd, f'ast://{target}?type=function', '--format', 'json'))
    got = {r['name']: r['provenance'] for r in data['results']}
    assert got == _EXPECTED


@pytest.mark.parametrize('spelling', ['relative', 'absolute'])
def test_hotspots_functions_share_file_paths_and_provenance(nested_target, spelling):
    cwd, root = nested_target
    target = 'tests/proj' if spelling == 'relative' else str(root)
    data = _json(_run_reveal_in(cwd, 'hotspots', target, '--format', 'json'))
    functions = {f['name']: (f['file'], f['provenance']) for f in data['function_hotspots']}
    assert functions == {
        'mainline': ('app/core.py', None),
        'vendored': ('vendor/lib.py', 'vendor'),
        'test_thing': ('tests/test_lib.py', 'test'),
    }
    # One path convention per answer: function entries match file entries.
    assert {f for f, _ in functions.values()} == {e['file'] for e in data['file_hotspots']}
