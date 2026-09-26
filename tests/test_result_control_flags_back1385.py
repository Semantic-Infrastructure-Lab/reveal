"""BACK-1385: `sort=`/`limit=` were declared universal but six adapters do not read them.

env://, python://, help://, cpanel://, domain:// and diff:// either glued `?limit=2` onto their
resource ("Element '?limit=2' not found", a path error) or dropped it with a warning. Now
`--sort`/`--limit` print a "no effect" note and a typed `?sort=`/`?limit=`/`?offset=` is a
clear error, decided by the adapter's HONORS_RESULT_CONTROL attribute.
"""
import json
import os
import subprocess
import sys

import pytest

import reveal.adapters  # noqa: F401  registers every adapter
from reveal.adapters.base import get_adapter_class, list_supported_schemes

OPTED_OUT = ['cpanel', 'diff', 'domain', 'env', 'help', 'python']


def run_reveal(*args):
    return subprocess.run([sys.executable, '-m', 'reveal.main', *args], capture_output=True,
                          text=True, encoding='utf-8', env={**os.environ, 'REVEAL_DISK_CACHE': '0'})


class TestOptOutSet:
    def test_only_the_known_adapters_opt_out(self):
        opted = sorted(s for s in list_supported_schemes()
                       if not getattr(get_adapter_class(s), 'HONORS_RESULT_CONTROL', True))
        assert opted == OPTED_OUT, "adding an opt-out needs a reason; update this list deliberately"


class TestTypedKeysAreRejected:
    URIS = {
        'env': 'env://?sort=name',
        'python': 'python://?limit=2',
        'help': 'help://?limit=3',
        'domain': 'domain://example.com?limit=2',
        'cpanel': 'cpanel://user@host?limit=2',
        'diff': 'diff://a.py:b.py?limit=2',
    }

    @pytest.mark.parametrize('scheme', OPTED_OUT)
    def test_clear_error_and_exit_1(self, scheme):
        proc = run_reveal(self.URIS[scheme])
        assert proc.returncode == 1
        assert f"{scheme}:// does not support" in proc.stderr
        assert 'Element' not in proc.stderr and 'Traceback' not in proc.stderr

    def test_offset_is_rejected_too_and_all_keys_are_named(self):
        proc = run_reveal('env://?sort=name&offset=2')
        assert proc.returncode == 1
        assert 'sort=/offset=' in proc.stderr

    def test_json_error_envelope(self):
        proc = run_reveal('env://?limit=2', '--format', 'json')
        assert proc.returncode == 1
        assert json.loads(proc.stdout)['meta']['errors'][0]['code'] == 'adapter_error'

    def test_other_query_keys_are_left_alone(self):
        # help://search reads its own ?search= key; only result-control keys are rejected.
        proc = run_reveal('help://search?search=ast')
        assert 'does not support' not in proc.stderr


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
