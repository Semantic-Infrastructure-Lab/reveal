"""BACK-1349: env forms the rule table cannot hold yet, found by the scanners.

`import.meta.env.X` (Vite, J12 in the BACK-1389 pass) and Swift's bare `getenv("X")` were not
reported. Negative controls: a local named like the environment is not the environment.
"""

import pytest

from reveal.adapters.surface import _scan_surface


def _env(name, source, tmp_path):
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    return [(e['name'], e['expr']) for e in _scan_surface(path)['surfaces']['env']]


def test_vite_import_meta_env_is_an_env_read(tmp_path):
    source = ('const a = import.meta.env.VITE_API_URL;\n'
              'const b = import.meta.env["VITE_KEY"];\n'
              'const c = process.env.NODE_ENV;\n')
    assert _env('a.ts', source, tmp_path) == [('VITE_API_URL', 'import.meta.env'),
                                              ('VITE_KEY', 'import.meta.env'),
                                              ('NODE_ENV', 'process.env')]


def test_import_meta_lookalikes_are_not_env_reads(tmp_path):
    source = ('const meta = { env: { A: 1 } };\n'
              'const a = meta.env.A;\n'
              'const u = import.meta.url;\n'
              'const m = import.meta.env.MODE.length;\n'
              'const h = import.meta.env.hasOwnProperty("X");\n'
              'const env = { B: 2 };\n'
              'const b = env.B;\n')
    assert _env('a.ts', source, tmp_path) == [('MODE', 'import.meta.env')]


def test_swift_bare_getenv_is_an_env_read(tmp_path):
    source = ('import Foundation\n'
              'let a = getenv("HOME")\n'
              'let b = ProcessInfo.processInfo.environment["PATH"]\n')
    assert _env('a.swift', source, tmp_path) == [('HOME', 'getenv'), ('PATH', 'ProcessInfo.environment')]


def test_swift_getenv_lookalikes_are_not_env_reads(tmp_path):
    source = ('import Foundation\n'
              'func f(key: String, shim: Shim) {\n'
              '  let a = getenv(key)\n'
              '  let b = shim.getenv("HOME")\n'
              '  let env = ["D": "1"]\n'
              '  let d = env["D"]\n'
              '}\n')
    assert _env('a.swift', source, tmp_path) == []
