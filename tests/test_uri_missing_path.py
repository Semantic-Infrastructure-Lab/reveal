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
from reveal.cli.routing.declared import declared_adapter_class
from reveal.cli.routing.uri import handle_uri

pytestmark = pytest.mark.component

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


# Every adapter that opts into the shared check, derived from the registry (BACK-1363).
# An adapter that should opt in but doesn't is caught by the contract harness, which
# probes every registered adapter with a missing resource
# (tests/test_output_contract_compliance.py::test_missing_resource_is_an_error).
PATH_ADAPTERS = _flagged_schemes()


def _missing_path_contract(scheme):
    adapter = declared_adapter_class(scheme)
    return (2, adapter.RESULT_TYPE) if adapter is not None else (1, scheme)


def _missing_path_uri(scheme):
    from reveal.utils.query_binding import encode_param_value
    adapter = declared_adapter_class(scheme)
    query = []
    for spec in adapter.PARAM_SPECS if adapter is not None else ():
        if spec.required:
            assert spec.examples, f'{scheme}/{spec.name}: path probe needs a valid required value'
            value = spec.examples[0].partition('=')[2]
            query.append(f'{spec.name}={encode_param_value(spec, value)}')
    return f'{scheme}://nonexistent_zz_1321' + ('?' + '&'.join(query) if query else '')


def test_default_is_not_a_path_adapter():
    assert adapters_base.ResourceAdapter.RESOURCE_IS_PATH is False


@pytest.mark.parametrize('scheme', PATH_ADAPTERS)
def test_missing_path_exits_with_error(scheme):
    code, out, err = _run(_missing_path_uri(scheme))
    assert code == _missing_path_contract(scheme)[0]
    assert f'Error ({scheme}://): Path not found: nonexistent_zz_1321' in err
    assert out == ''


@pytest.mark.parametrize('scheme', PATH_ADAPTERS)
def test_missing_path_json_emits_error_envelope(scheme):
    code, out, _ = _run(_missing_path_uri(scheme), format='json')
    expected_code, expected_type = _missing_path_contract(scheme)
    assert code == expected_code
    payload = json.loads(out)
    assert 'Path not found' in payload['error']
    assert payload['type'] == expected_type


def test_query_string_is_not_part_of_the_path():
    # 'nonexistent_zz?type=env' must be judged on 'nonexistent_zz' alone.
    code, _, err = _run('surface://nonexistent_zz_1321?type=env')
    assert code == 2
    assert 'Path not found: nonexistent_zz_1321\n' in err


def test_existing_path_and_query_still_work(tmp_path):
    (tmp_path / 'a.py').write_text("import os\nX = os.environ.get('K')\n")
    code, out, _ = _run(f'surface://{tmp_path}?type=env')
    assert code == 0
    assert 'K' in out


def test_empty_resource_means_cwd_not_an_error(tmp_path, monkeypatch):
    # A small cwd: from the repo root this scanned all of reveal (~40 s under xdist).
    (tmp_path / 'app.py').write_text('import os\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    code, _, err = _run('surface://')
    assert code == 0
    assert 'Path not found' not in err


@pytest.mark.parametrize('uri', [
    'stats://nonexistent_zz_1321',
    'classify://nonexistent_zz_1321',
])
def test_adapters_with_their_own_check_still_exit_1(uri):
    code, _, _ = _run(uri)
    assert code == 1


def test_patches_is_a_declared_noun_and_rejects_a_missing_path_with_exit_2():
    """patches adopted the declared path (BACK-2160): a request naming nothing is rejected before analysis."""
    code, _, _ = _run('patches://nonexistent_zz_1321')
    assert code == 2


def test_calls_name_shorthand_is_not_a_missing_path(tmp_path):
    # BACK-1499: `calls://path:name` was rejected as "Path not found: path:name"
    # because the check ran before the adapter split off `:name`.
    src = tmp_path / 'mod.py'
    src.write_text('def helper():\n    pass\n\n\ndef main():\n    helper()\n', encoding='utf-8')
    code, out, err = _run(f'calls://{src}:helper')
    assert code == 0, err
    assert 'Callers of: helper' in out
    assert 'main' in out


def test_calls_name_shorthand_on_missing_path_still_errors():
    code, _, err = _run('calls://nonexistent_zz_1499.py:helper')
    assert code == 2  # a declared noun rejects a missing path before analysis (BACK-2066)
    assert 'Path not found: nonexistent_zz_1499.py:helper' in err
