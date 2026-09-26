"""BACK-1385: `sort=`/`limit=` were declared universal but six adapters do not read them.

env://, python://, help://, cpanel://, domain:// and diff:// either glued `?limit=2` onto their
resource ("Element '?limit=2' not found", a path error) or dropped it; reveal:// ignored it
silently. For adapters with HONORS_RESULT_CONTROL = False, `--sort`/`--limit` now print a
"no effect" note, and a typed `?sort=`/`?limit=`/`?offset=` is stripped with the standard
"Unknown query param ... ignored" warning and the query runs -- the same contract every other
adapter gives an unsupported param.
"""
import json
import os
import subprocess
import sys

import pytest

import reveal.adapters  # noqa: F401  registers every adapter
from reveal.adapters.base import get_adapter_class, list_supported_schemes

OPTED_OUT = ['cpanel', 'diff', 'domain', 'env', 'help', 'python', 'reveal']


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
        'env': 'env://?sort=name',
        'python': 'python://?limit=2',
        'help': 'help://?limit=3',
        'domain': 'domain://example.com?limit=2',
        'cpanel': 'cpanel://user@host?limit=2',
        'diff': 'diff://a.py:b.py?limit=2',
        'reveal': 'reveal://?limit=1',
    }

    @pytest.mark.parametrize('scheme', OPTED_OUT)
    def test_standard_warning_and_no_mangled_resource(self, scheme):
        proc = run_reveal(self.URIS[scheme])
        key = self.URIS[scheme].rpartition('?')[2].partition('=')[0]
        assert f"Unknown query param '{key}' for {scheme}:// — ignored." in proc.stderr
        assert "'?" not in proc.stderr  # the key never reached the resource
        assert 'Element' not in proc.stderr and 'Traceback' not in proc.stderr

    @pytest.mark.parametrize('uri,expected', [('env://?sort=name', 'Environment Variables'),
                                              ('reveal://?limit=1', 'Reveal Internal Structure')])
    def test_query_still_runs(self, uri, expected):
        proc = run_reveal(uri)
        assert proc.returncode == 0, proc.stderr
        assert expected in proc.stdout

    def test_every_key_is_named(self):
        proc = run_reveal('env://?sort=name&offset=2')
        assert "'sort'" in proc.stderr and "'offset'" in proc.stderr

    def test_json_output_is_the_result_not_an_error(self):
        proc = run_reveal('env://?limit=2', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert not json.loads(proc.stdout).get('meta', {}).get('errors')

    def test_other_query_keys_survive(self):
        proc = run_reveal('help://search?search=ast&limit=2')
        assert proc.returncode == 0, proc.stderr
        assert "Help Search: 'ast'" in proc.stdout
        assert "Unknown query param 'limit' for help:// — ignored." in proc.stderr
        assert 'Valid params' not in proc.stderr  # help:// has no schema to list


class TestStripHelper:
    from reveal.cli.routing.flag_specs import strip_result_control_keys as strip

    def test_strips_only_result_control_keys(self):
        env = get_adapter_class('env')
        assert type(self).strip('x?a=1&limit=2&b&sort=n', env) == ('x?a=1&b', ['limit', 'sort'])

    def test_drops_empty_query(self):
        assert type(self).strip('?limit=2', get_adapter_class('env')) == ('', ['limit'])

    def test_passes_through_for_adapters_that_receive_them(self):
        assert type(self).strip('.?limit=2', get_adapter_class('ast')) == ('.?limit=2', [])


class TestCliFlagsNoLongerBreakTheUri:
    @pytest.mark.parametrize('scheme,flag', [('env://', '--limit'), ('python://', '--sort')])
    def test_note_instead_of_element_not_found(self, scheme, flag):
        value = '2' if flag == '--limit' else 'name'
        proc = run_reveal(scheme, flag, value)
        assert proc.returncode == 0, proc.stderr
        assert f"Note: {flag} has no effect on {scheme}" in proc.stderr
        assert 'Element' not in proc.stderr

    def test_flag_without_value_is_silent(self):
        proc = run_reveal('env://')
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
