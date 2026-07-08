"""BACK-507: adapters warn (to stderr) on unrecognized query params.

Closed-param adapters read a fixed key set via ``.get()`` and silently ignore
the rest, so a typo'd or unsupported param (the repro: ``stats://?complexity=true``,
where the real params are ``min_complexity``/``max_complexity``) used to return a
valid-looking-but-wrong result with no signal. These tests pin:

  1. the repro now warns and still returns a result (warning, not error);
  2. every *declared* schema param on a wired adapter stays silent — which also
     guards against schema/code drift (a param the code reads but the schema
     stops declaring would start false-warning, and this test would catch it);
  3. mixed adapters (stats) don't flag valid filter expressions.
"""

import io
import sys
from contextlib import redirect_stderr
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402  (tests/test_at_file_syntax.py idiom)


def _stderr_of(fn):
    buf = io.StringIO()
    with redirect_stderr(buf):
        try:
            fn()
        except Exception:
            pass  # construction/parse errors are irrelevant; we only inspect stderr
    return buf.getvalue()


def _warns(fn):
    return 'Unknown query param' in _stderr_of(fn)


# ── The reported repro ────────────────────────────────────────────────────────

class TestStatsRepro:
    def test_unknown_stats_param_warns(self, tmp_path):
        (tmp_path / 'a.py').write_text('def f():\n    pass\n')
        result = _run_reveal_direct(f'stats://{tmp_path}?complexity=true')
        assert "Unknown query param 'complexity'" in result.stderr
        # Warning, not error: the result is still produced and exit code is clean.
        assert result.returncode == 0
        assert 'Statistics' in result.stdout or 'Files' in result.stdout

    def test_valid_stats_param_silent(self, tmp_path):
        (tmp_path / 'a.py').write_text('def f():\n    pass\n')
        result = _run_reveal_direct(f'stats://{tmp_path}?hotspots=true')
        assert 'Unknown query param' not in result.stderr

    def test_stats_filter_expression_not_flagged(self, tmp_path):
        """A filter (min_complexity>0) is not a fixed param and must not warn."""
        (tmp_path / 'a.py').write_text('def f():\n    if x:\n        return 1\n')
        result = _run_reveal_direct(f'stats://{tmp_path}?min_complexity>0')
        assert 'Unknown query param' not in result.stderr

    def test_stats_result_control_not_flagged(self, tmp_path):
        (tmp_path / 'a.py').write_text('def f():\n    pass\n')
        result = _run_reveal_direct(f'stats://{tmp_path}?hotspots=true&limit=5&sort=complexity')
        assert 'Unknown query param' not in result.stderr


# ── Schema/code drift guard across every wired adapter ────────────────────────

# (adapter class import path, constructor callable factory). The factory builds
# an instance from a query string so we can feed it each declared param.
def _wired_adapters():
    from reveal.adapters.ssl.adapter import SSLAdapter
    from reveal.adapters.imports import ImportsAdapter
    from reveal.adapters.depends import DependsAdapter
    from reveal.adapters.calls.adapter import CallsAdapter
    from reveal.adapters.patches.adapter import PatchesAdapter
    from reveal.adapters.stats.adapter import StatsAdapter

    return {
        'ssl': (SSLAdapter, lambda q: SSLAdapter(f'ssl://example.com?{q}')),
        'imports': (ImportsAdapter, lambda q: ImportsAdapter('.', q)),
        'depends': (DependsAdapter, lambda q: DependsAdapter('.', q)),
        'calls': (CallsAdapter, lambda q: CallsAdapter('.', q)),
        'patches': (PatchesAdapter, lambda q: PatchesAdapter('.', q)),
        'stats': (StatsAdapter, lambda q: StatsAdapter('.', q)),
    }


@pytest.mark.parametrize('adapter_name', list(_wired_adapters().keys()))
def test_declared_params_never_warn(adapter_name):
    """Every param in an adapter's schema must construct without a warning.

    This is the schema/code drift guard: if a param the adapter actually reads
    were dropped from (or never added to) the schema, feeding it here would
    trip the unknown-param warning and fail this test.
    """
    cls, factory = _wired_adapters()[adapter_name]
    schema = cls.get_schema() or {}
    params = (schema.get('query_params') or {})
    assert params, f'{adapter_name} should declare query_params'

    for pname in params:
        # Skip filter-syntax template keys (defensive; wired adapters are fixed-set).
        if any(c in pname for c in '<>~!=*.'):
            continue
        stderr = _stderr_of(lambda: factory(f'{pname}=x'))
        assert 'Unknown query param' not in stderr, (
            f'{adapter_name}: declared param {pname!r} produced an unknown-param '
            f'warning -> schema/code drift. stderr:\n{stderr}'
        )


@pytest.mark.parametrize('adapter_name', list(_wired_adapters().keys()))
def test_typo_param_warns(adapter_name):
    """A clearly-unknown param triggers the warning on every wired adapter."""
    cls, factory = _wired_adapters()[adapter_name]
    stderr = _stderr_of(lambda: factory('definitely_not_a_real_param_xyz=1'))
    assert 'Unknown query param' in stderr, (
        f'{adapter_name}: a bogus param did not warn. stderr:\n{stderr}'
    )
