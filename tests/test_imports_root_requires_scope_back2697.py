"""Imports ``root`` pins the scan root the climb would find, so it needs ``scope=root`` (BACK-2697).

Under ``scope=path`` the requested path is the scan root and ``root`` is never read: the request conflicts with itself,
an invalid request naming both before analysis (the BACK-2656 requires ruling, as Metrics ``since`` with ``churn off``),
on every form. Before, the answer warned ``?root=. is ignored under scope=path`` and exited 0. The declaration is the
generic ``ParamSpec.requires`` on ``root``; the hand warning is gone.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.errors import RequestValidationError

CONFLICT = "control 'root' requires scope=root; this request gives scope=path"


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'app.py').write_text('import core\n', encoding='utf-8')
    (tmp_path / 'pkg' / 'core.py').write_text('VALUE = 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


@pytest.mark.parametrize('argv', [
    ('imports://pkg?scope=path&root=.',),
    ('imports://pkg?importers&scope=path&root=.',),
    ('imports', 'pkg', '--scope', 'path', '--root', '.'),
    ('imports', 'pkg', '--importers', '--scope', 'path', '--root', '.'),
    ('imports://pkg?scope=path', '--root', '.'),
    ('imports://pkg?root=.', '--scope', 'path'),
])
def test_root_with_scope_path_is_an_invalid_request_naming_both(proj, argv):
    run, doc = _run(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout[:300], run.stderr)
    assert CONFLICT in run.stderr, run.stderr
    assert 'is ignored under scope=path' not in run.stdout + run.stderr


def test_the_api_refuses_the_same_request_on_both_forms(proj):
    from reveal import api
    with pytest.raises(RequestValidationError, match=CONFLICT):
        api.query('imports://pkg?scope=path&root=.')
    with pytest.raises(RequestValidationError, match=CONFLICT):
        api.query('imports://pkg?scope=path', root='.')
    with pytest.raises(RequestValidationError, match=CONFLICT):
        api.query('imports', 'pkg', scope='path', root='.')


@pytest.mark.parametrize('argv', [
    ('imports://pkg?root=.',),                      # scope=root is the default
    ('imports://pkg?scope=root&root=.',),
    ('imports://pkg?scope=path',),                  # scope=path alone
    ('imports', 'pkg', '--scope', 'path'),
    ('imports', 'pkg', '--root', '.'),
])
def test_root_under_scope_root_and_scope_path_alone_answer(proj, argv):
    run, doc = _run(*argv)
    assert run.returncode == 0, run.stderr
    assert not any(w.get('type') == 'root_rejected' for w in doc['meta']['warnings']), doc['meta']['warnings']


def test_the_requirement_is_declared_and_published():
    from reveal.adapters.imports import ImportsAdapter
    [root] = [spec for spec in ImportsAdapter.PARAM_SPECS if spec.name == 'root']
    assert root.requires == ('scope=root',)
    assert root.schema()['requires'] == ['scope=root']
