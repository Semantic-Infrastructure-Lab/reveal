"""BACK-1321: a nonexistent path on a path-taking adapter is an error, not an
empty result.

`reveal imports://nonexistent`, `ast://`, `surface://`, `calls://`, `depends://`
and friends printed "Total: 0" and exited 0, so a typo'd path read as a
confirmed-empty answer. `stats://`, `git://` and the bare path already exited 1.
The shared check keys off `ResourceAdapter.RESOURCE_IS_PATH`.
"""

import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import pytest

from reveal.adapters import base as adapters_base
from reveal.cli.defaults import _default_args
from reveal.cli.routing.uri import handle_uri

pytestmark = pytest.mark.component

# Every adapter whose resource is a filesystem path and that had no check of
# its own. Pinned so dropping the flag from one is a deliberate act.
PATH_ADAPTERS = sorted([
    'architecture', 'ast', 'calls', 'contracts', 'deps', 'depends', 'hotspots',
    'imports', 'overview', 'pack', 'surface', 'testability',
])


def _run(uri, **overrides):
    out, err = StringIO(), StringIO()
    code = 0
    with redirect_stdout(out), redirect_stderr(err):
        try:
            handle_uri(uri, None, _default_args(**overrides))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def _flagged_schemes():
    from reveal import adapters  # noqa: F401  (registers every adapter)
    return sorted(
        scheme for scheme in adapters_base.list_supported_schemes()
        if getattr(adapters_base.get_adapter_class(scheme), 'RESOURCE_IS_PATH', False) is True
    )


def test_flagged_adapters_are_the_expected_set():
    assert _flagged_schemes() == PATH_ADAPTERS


def test_default_is_not_a_path_adapter():
    assert adapters_base.ResourceAdapter.RESOURCE_IS_PATH is False


@pytest.mark.parametrize('scheme', PATH_ADAPTERS)
def test_missing_path_exits_1_with_error(scheme):
    code, out, err = _run(f'{scheme}://nonexistent_zz_1321')
    assert code == 1
    assert f'Error ({scheme}://): Path not found: nonexistent_zz_1321' in err
    assert out == ''


@pytest.mark.parametrize('scheme', PATH_ADAPTERS)
def test_missing_path_json_emits_error_envelope(scheme):
    code, out, _ = _run(f'{scheme}://nonexistent_zz_1321', format='json')
    assert code == 1
    payload = json.loads(out)
    assert 'Path not found' in payload['error']
    assert payload['type'] == scheme


def test_query_string_is_not_part_of_the_path():
    # 'nonexistent_zz?type=env' must be judged on 'nonexistent_zz' alone.
    code, _, err = _run('surface://nonexistent_zz_1321?type=env')
    assert code == 1
    assert 'Path not found: nonexistent_zz_1321\n' in err


def test_existing_path_and_query_still_work(tmp_path):
    (tmp_path / 'a.py').write_text("import os\nX = os.environ.get('K')\n")
    code, out, _ = _run(f'surface://{tmp_path}?type=env')
    assert code == 0
    assert 'K' in out


def test_empty_resource_means_cwd_not_an_error():
    code, _, err = _run('surface://')
    assert code == 0
    assert 'Path not found' not in err


@pytest.mark.parametrize('uri', [
    'stats://nonexistent_zz_1321',
    'classify://nonexistent_zz_1321',
    'patches://nonexistent_zz_1321',
])
def test_adapters_with_their_own_check_still_exit_1(uri):
    code, _, _ = _run(uri)
    assert code == 1
