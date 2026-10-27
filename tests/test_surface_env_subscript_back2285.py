"""BACK-2285: Python ``os.environ[k]`` with a non-literal key is reported like the call forms.

``os.getenv(k)`` and ``os.environ.get(k)`` already report ``name`` = the key's source text; the
subscript form (``ast.Subscript``, the BACK-777 path) dropped any key that was not a literal.
"""
import tempfile
import textwrap
import unittest
from pathlib import Path

from reveal.adapters.ast.nav_surface import scan_file_surface


def _env_rows(source: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'app.py'
        path.write_text(textwrap.dedent(source), encoding='utf-8')
        return scan_file_surface(str(path))['env']


class TestEnvironSubscriptNonLiteralKey(unittest.TestCase):

    def test_variable_key_read_is_reported_like_the_call_forms(self):
        rows = _env_rows('''\
            import os
            def f(k):
                a = os.environ[k]
                b = os.getenv(k)
                c = os.environ.get(k)
        ''')
        by_line = {r['line']: (r['name'], r['expr']) for r in rows}
        self.assertEqual(by_line.get(3), ('k', 'os.environ[...]'))
        self.assertEqual(by_line.get(4), ('k', 'os.getenv'))
        self.assertEqual(by_line.get(5), ('k', 'os.environ.get'))

    def test_interpolated_and_attribute_keys_use_source_text(self):
        rows = _env_rows('''\
            import os
            from os import environ
            def f(k, cfg):
                os.environ[f'P_{k}'] = '1'
                return environ[cfg.key]
        ''')
        names = sorted(r['name'] for r in rows)
        self.assertEqual(names, ["cfg.key", "f'P_{k}'"])

    def test_literal_key_unchanged(self):
        # Negative control: the literal form keeps the bare key text (BACK-777).
        rows = _env_rows('''\
            import os
            X = os.environ['DATABASE_URL']
        ''')
        self.assertEqual([(r['name'], r['expr'], r['line']) for r in rows],
                         [('DATABASE_URL', 'os.environ[...]', 2)])

    def test_other_mappings_with_variable_keys_not_reported(self):
        # Negative control: only the environment mapping is a surface.
        rows = _env_rows('''\
            import os
            def f(k, d, env):
                return d[k], env[k], os.path[k]
        ''')
        self.assertEqual(rows, [])


if __name__ == '__main__':
    unittest.main()
