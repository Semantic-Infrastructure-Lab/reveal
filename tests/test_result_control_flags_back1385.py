"""BACK-1385: `sort=`/`limit=` were declared universal but six adapters do not read them.

env://, python:// (removed since, BACK-2225), help://, cpanel://, domain:// and diff:// either glued `?limit=2` onto their
resource ("Element '?limit=2' not found", a path error) or dropped it; reveal:// ignored it
silently. For adapters with HONORS_RESULT_CONTROL = False, `--sort`/`--limit` now print a
"no effect" note, and a typed `?sort=`/`?limit=`/`?offset=` is stripped with the standard
"Unknown query param ... ignored" warning and the query runs -- the same contract every other
adapter gives an unsupported param. env:// left the set when it was declared (BACK-2626): it takes no
control, so each of these exits 2 naming it (tests/test_sqlite_env_vocabulary_back2626.py). help:// and reveal:// left it
the same way when they were declared (BACK-2767): help takes search and top only, reveal:// no control. diff:// left it
when it was declared (BACK-2214): it takes exclude only (tests/test_diff_vocabulary_back2214.py). The run-anyway cases
use a plugin adapter that declares nothing (tests/undeclared_plugin.py), the undeclared path that outlives the cut.
"""
import json
import os
import subprocess
import sys

import pytest

import reveal.adapters  # noqa: F401  registers every adapter
from conftest import _run_reveal_direct
from undeclared_plugin import UndeclaredPluginAdapter, undeclared_plugin  # noqa: F401  (undeclared_plugin is a fixture)
from reveal.adapters.base import get_adapter_class, list_supported_schemes

OPTED_OUT = ['cpanel', 'domain']


def run_reveal(*args):
    return subprocess.run([sys.executable, '-m', 'reveal.main', *args], capture_output=True,
                          text=True, encoding='utf-8', env={**os.environ, 'REVEAL_DISK_CACHE': '0'})


class TestOptOutSet:
    def test_only_the_known_adapters_opt_out(self):
        opted = sorted(s for s in list_supported_schemes()
                       if not getattr(get_adapter_class(s), 'HONORS_RESULT_CONTROL', True))
        assert opted == OPTED_OUT, "opt out only when the resource cannot carry a query key"


class TestTypedKeysAreStrippedWithAWarning:
    URIS = {
        'domain': 'domain://example.com?limit=2',
        'cpanel': 'cpanel://user@host?limit=2',
    }

    @pytest.mark.parametrize('scheme', OPTED_OUT)
    def test_standard_warning_and_no_mangled_resource(self, scheme):
        proc = run_reveal(self.URIS[scheme])
        key = self.URIS[scheme].rpartition('?')[2].partition('=')[0]
        assert f"Unknown query param '{key}' for {scheme}:// — ignored." in proc.stderr
        assert "'?" not in proc.stderr  # the key never reached the resource
        assert 'Element' not in proc.stderr and 'Traceback' not in proc.stderr

    @pytest.fixture
    def plugin(self, undeclared_plugin):  # noqa: F811
        return f'{undeclared_plugin}://x'

    def test_a_plugin_gets_the_standard_warning(self, plugin):
        proc = _run_reveal_direct(plugin + '?limit=2')
        assert "Unknown query param 'limit' for undeclared:// — ignored." in proc.stderr
        assert proc.stdout.strip() == 'x'  # the key never reached the resource

    @pytest.mark.parametrize('query', ['?sort=name', '?limit=1'])
    def test_query_still_runs(self, plugin, query):
        proc = _run_reveal_direct(plugin + query)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == 'x'

    def test_every_key_is_named(self, plugin):
        proc = _run_reveal_direct(plugin + '?sort=name&offset=2')
        assert "'sort'" in proc.stderr and "'offset'" in proc.stderr

    def test_json_output_is_the_result_not_an_error(self, plugin):
        proc = _run_reveal_direct(plugin + '?limit=2', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert not json.loads(proc.stdout).get('meta', {}).get('errors')


class TestDeclaredSchemesRefuseTheKeys:
    """help:// and reveal:// left the opt-out set when they were declared (BACK-2767): a result-control key or flag is
    an unsupported control, exit 2 naming it and the controls the scheme takes (it was stripped with a warning)."""

    @pytest.mark.parametrize('argv,named', [(['help://search?search=ast&limit=2'], "'limit'"),
                                            (['reveal://?sort=name&offset=2'], "'sort'"),
                                            (['reveal://', '--limit', '2'], "'limit'"),
                                            (['help://', '--sort', 'name'], "'sort'")])
    def test_exit_2_naming_the_control(self, argv, named):
        proc = run_reveal(*argv, '--format', 'json')
        assert proc.returncode == 2, proc.stderr
        assert named in proc.stderr and 'supported controls' in proc.stderr
        assert json.loads(proc.stdout)['meta']['errors'][0]['code'] == 'invalid_request'

    def test_the_declared_keys_still_answer(self):
        proc = run_reveal('help://search?search=ast&top=2')
        assert proc.returncode == 0, proc.stderr
        assert "Help Search: 'ast'" in proc.stdout


class TestStripHelper:
    from reveal.cli.routing.flag_specs import strip_result_control_keys as strip

    def test_strips_only_result_control_keys(self):
        assert type(self).strip('x?a=1&limit=2&b&sort=n', UndeclaredPluginAdapter) == ('x?a=1&b', ['limit', 'sort'])

    def test_drops_empty_query(self):
        assert type(self).strip('?limit=2', UndeclaredPluginAdapter) == ('', ['limit'])

    def test_passes_through_for_adapters_that_receive_them(self):
        assert type(self).strip('.?limit=2', get_adapter_class('ast')) == ('.?limit=2', [])


class TestCliFlagsNoLongerBreakTheUri:
    @pytest.fixture
    def plugin(self, undeclared_plugin):  # noqa: F811
        return f'{undeclared_plugin}://x'

    @pytest.mark.parametrize('flag', ['--limit', '--sort'])
    def test_note_instead_of_element_not_found(self, plugin, flag):
        value = '2' if flag == '--limit' else 'name'
        proc = _run_reveal_direct(plugin, flag, value)
        assert proc.returncode == 0, proc.stderr
        assert f"Note: {flag} has no effect on undeclared://" in proc.stderr
        assert 'Element' not in proc.stderr and proc.stdout.strip() == 'x'

    def test_flag_without_value_is_silent(self, plugin):
        proc = _run_reveal_direct(plugin)
        assert proc.returncode == 0
        assert 'has no effect' not in proc.stderr


class TestHonoringAdaptersUnchanged:
    """Positive control: a fix that rejected everything would also 'pass' the tests above."""

    @pytest.fixture
    def tree(self, tmp_path):
        for name in 'abc':
            (tmp_path / f'{name}.py').write_text("def f():\n    return 1\n", encoding='utf-8')
        return tmp_path

    def test_typed_limit_still_applies(self, tree):
        proc = run_reveal(f'ast://{tree}?limit=1', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert 'does not support' not in proc.stderr
        assert len(json.loads(proc.stdout).get('results', [])) == 1

    def test_cli_limit_still_injected(self, tree):
        proc = run_reveal(f'ast://{tree}', '--limit', '2', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert len(json.loads(proc.stdout).get('results', [])) == 2
        assert 'has no effect' not in proc.stderr
