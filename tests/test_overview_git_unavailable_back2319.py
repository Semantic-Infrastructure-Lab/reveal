"""BACK-2319: ``overview`` on an install without pygit2 is a disclosed gap, not a failed composition.

A default ``pip install reveal-cli`` has no pygit2 (it is the ``git`` extra). overview's git-root
probe raised ImportError, was recorded as ``E_COMPOSE`` with confidence 0.0, and the README's
first-screen ``reveal overview .`` exited 3 where 0.131.0 exited 0. A missing optional dependency
is the same kind of fact as stats' ``churn_unavailable``: the section is absent and a
``meta.warnings`` entry says why and how to install it. A repository that cannot be opened, or an
ImportError that is not the absent extra, is still a failed composition.
"""
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from reveal.adapters.git import GitAdapter
from reveal.adapters.overview import OverviewAdapter
from reveal.cli.defaults import _default_args
from reveal.cli.routing.uri import handle_uri
from reveal.utils.results import outcome_of

pytestmark = pytest.mark.component

NO_PYGIT2 = 'reveal.adapters.git.adapter.PYGIT2_AVAILABLE'


def _project(tmp):
    """A directory with one analyzable file, so nothing but git can lower the confidence."""
    Path(tmp, 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    return tmp


def _overview(query='no_imports=true'):
    with tempfile.TemporaryDirectory() as tmp:
        return OverviewAdapter(_project(tmp), query).get_structure()


def _warnings(result, kind):
    return [w for w in (result.get('meta') or {}).get('warnings') or [] if w.get('type') == kind]


def _errors(result):
    return (result.get('meta') or {}).get('errors') or []


def test_absent_pygit2_is_a_warning_with_the_install_hint():
    with patch(NO_PYGIT2, False):
        result = _overview()
    assert _errors(result) == []
    (warning,) = _warnings(result, 'git_unavailable')
    assert 'pygit2' in warning['message'] and 'reveal-cli[git]' in warning['message']
    assert outcome_of(result) == 'ok'
    assert result['meta']['confidence'] == 1.0


def test_absent_pygit2_exits_zero_and_says_so_in_text_and_json():
    with tempfile.TemporaryDirectory() as tmp, patch(NO_PYGIT2, False):
        _project(tmp)
        for fmt in ('text', 'json'):
            out, err = StringIO(), StringIO()
            code = 0
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    handle_uri(f'overview://{tmp}?no_imports=true', None, _default_args(format=fmt))
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 1
            assert code == 0, (fmt, code, err.getvalue()[:300])
            assert 'reveal-cli[git]' in out.getvalue(), fmt
        payload = json.loads(out.getvalue())
        assert any(w.get('type') == 'git_unavailable' for w in payload['meta']['warnings'])
        assert not payload['meta'].get('errors')


def test_a_request_that_skips_git_does_not_report_it_missing():
    with patch(NO_PYGIT2, False):
        result = _overview('no_imports=true&no_git=true')
    assert _warnings(result, 'git_unavailable') == []
    assert _errors(result) == []


def test_an_installed_pygit2_adds_no_warning():
    with patch(NO_PYGIT2, True):
        result = _overview()
    assert _warnings(result, 'git_unavailable') == []


def test_an_import_error_that_is_not_the_absent_extra_is_still_a_failed_composition():
    """Control: pygit2 is there but loading it failed. That is not 'not installed'."""
    with patch(NO_PYGIT2, True), \
            patch.object(GitAdapter, 'get_metadata', side_effect=ImportError('libgit2.so: cannot open')):
        result = _overview()
    assert [e['code'] for e in _errors(result)] == ['E_COMPOSE']
    assert _warnings(result, 'git_unavailable') == []
    assert result['meta']['confidence'] < 1.0
