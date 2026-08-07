"""Parse-failure visibility for the nav_surface_*/nav_contracts_* scanners.

Each scanner used to catch a tree-sitter parse failure with a bare
'except Exception: return <empty>', logged nowhere — a crashed parse
rendered as a clean, valid, empty result, indistinguishable from a file that
genuinely has no findings. Same disease as BACK-979/981/982/984/991; this
cluster (BACK-990) covers 14 sites across 11 languages that BACK-982's
imports-analyzer fix never touched. Fix: log a warning (still returns the
same empty shape — no contract change) so the failure is visible.
"""

import importlib
from unittest.mock import patch

import pytest

# (module path, function name, expected empty result on parse failure)
_SURFACE_SCANNERS = [
    ('reveal.adapters.ast.nav_surface_php', 'scan_file_surface_php',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': []}),
    ('reveal.adapters.ast.nav_surface_java', 'scan_file_surface_java',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': []}),
    ('reveal.adapters.ast.nav_surface_csharp', 'scan_file_surface_csharp',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': []}),
    ('reveal.adapters.ast.nav_surface_rust', 'scan_file_surface_rust',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': []}),
    ('reveal.adapters.ast.nav_surface_swift', 'scan_file_surface_swift',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': []}),
    ('reveal.adapters.ast.nav_surface_go', 'scan_file_surface_go',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': []}),
    ('reveal.adapters.ast.nav_surface_ruby', 'scan_file_surface_ruby',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': []}),
    ('reveal.adapters.ast.nav_surface_cpp', 'scan_file_surface_cpp',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': []}),
    ('reveal.adapters.ast.nav_surface_kotlin', 'scan_file_surface_kotlin',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': []}),
    ('reveal.adapters.ast.nav_surface_ts', 'scan_file_surface_ts',
     {'cli': [], 'http': [], 'env': [], 'network': [], 'db': [], 'sdk': [], 'fs': [],
      'subprocess': [], 'mcp': []}),
]

_CONTRACTS_SCANNERS = [
    ('reveal.adapters.ast.nav_contracts_ruby', 'scan_file_contracts_ruby',
     {'modules': [], 'classes': []}),
    ('reveal.adapters.ast.nav_contracts_rust', 'scan_file_contracts_rust',
     {'interfaces': [], 'impls': []}),
    ('reveal.adapters.ast.nav_contracts_cpp', 'scan_file_contracts_cpp',
     {'classes': []}),
    ('reveal.adapters.ast.nav_contracts_go', 'scan_file_contracts_go',
     {'interfaces': [], 'structs': [], 'methods': []}),
]

_ALL_SCANNERS = _SURFACE_SCANNERS + _CONTRACTS_SCANNERS


@pytest.mark.parametrize('module_path,func_name,expected_empty', _ALL_SCANNERS,
                          ids=[m.rsplit('.', 1)[-1] for m, _, _ in _ALL_SCANNERS])
def test_parse_failure_logs_warning_and_returns_empty_shape(
    module_path, func_name, expected_empty, tmp_path, caplog
):
    module = importlib.import_module(module_path)
    scan_fn = getattr(module, func_name)

    fake_file = tmp_path / 'sample.src'
    fake_file.write_text('irrelevant — get_parser is mocked to raise')

    with patch('tree_sitter_language_pack.get_parser', side_effect=RuntimeError('grammar unavailable')):
        with caplog.at_level('WARNING', logger=module_path):
            result = scan_fn(str(fake_file))

    assert result == expected_empty, f'{func_name}: contract shape changed on parse failure'
    assert any(str(fake_file) in r.message for r in caplog.records), (
        f'{func_name}: parse failure produced no visible warning (BACK-990)'
    )
    assert all(r.levelname == 'WARNING' for r in caplog.records)
