"""Tests for adapter plugin discovery (BACK-256)."""

import sys
import tempfile
import unittest
from pathlib import Path

from reveal.adapters.base import (
    _adapter_plugins_loaded,
    _load_adapter_plugin_dir,
    _reset_adapter_plugin_discovery,
    _ADAPTER_REGISTRY,
    discover_adapter_plugins,
    get_adapter_class,
)


class TestDiscoverAdapterPlugins(unittest.TestCase):

    def setUp(self):
        _reset_adapter_plugin_discovery()
        # Remove any test plugin schemes registered by previous tests
        for key in list(_ADAPTER_REGISTRY.keys()):
            if key.startswith('test_plugin_'):
                del _ADAPTER_REGISTRY[key]
        # Remove cached plugin modules
        for key in list(sys.modules.keys()):
            if key.startswith('reveal_plugin_adapter_'):
                del sys.modules[key]

    def _write_plugin(self, adapters_dir: Path, scheme: str) -> Path:
        """Write a minimal adapter package into adapters_dir/<scheme>/."""
        pkg = adapters_dir / scheme
        pkg.mkdir(parents=True)
        (pkg / '__init__.py').write_text(
            f'from .adapter import TestAdapter\n'
        )
        (pkg / 'adapter.py').write_text(
            f'from reveal.adapters.base import ResourceAdapter, register_adapter\n\n'
            f'@register_adapter("{scheme}")\n'
            f'class TestAdapter(ResourceAdapter):\n'
            f'    def get_structure(self, **kw): return {{}}\n'
        )
        return pkg

    def test_no_plugin_dir_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            discover_adapter_plugins(cwd=Path(tmp))
        # No error, no new schemes

    def test_loads_plugin_from_cwd_reveal_adapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapters_dir = Path(tmp) / '.reveal' / 'adapters'
            adapters_dir.mkdir(parents=True)
            self._write_plugin(adapters_dir, 'test_plugin_cwd')
            discover_adapter_plugins(cwd=Path(tmp))
        self.assertIn('test_plugin_cwd', _ADAPTER_REGISTRY)

    def test_get_adapter_class_triggers_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapters_dir = Path(tmp) / '.reveal' / 'adapters'
            adapters_dir.mkdir(parents=True)
            self._write_plugin(adapters_dir, 'test_plugin_lazy')
            # Patch cwd so discover_adapter_plugins finds the plugin
            import unittest.mock as mock
            with mock.patch('pathlib.Path.cwd', return_value=Path(tmp)):
                cls = get_adapter_class('test_plugin_lazy')
        self.assertIsNotNone(cls)
        self.assertEqual(cls.__name__, 'TestAdapter')

    def test_once_per_process_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapters_dir = Path(tmp) / '.reveal' / 'adapters'
            adapters_dir.mkdir(parents=True)
            self._write_plugin(adapters_dir, 'test_plugin_once')
            discover_adapter_plugins(cwd=Path(tmp))
            # Second call with a different dir containing another plugin — should not load
            adapters_dir2 = Path(tmp) / 'other' / '.reveal' / 'adapters'
            adapters_dir2.mkdir(parents=True)
            self._write_plugin(adapters_dir2, 'test_plugin_once_b')
            discover_adapter_plugins(cwd=Path(tmp) / 'other')
        self.assertIn('test_plugin_once', _ADAPTER_REGISTRY)
        self.assertNotIn('test_plugin_once_b', _ADAPTER_REGISTRY)

    def test_broken_plugin_logs_warning_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapters_dir = Path(tmp) / '.reveal' / 'adapters'
            adapters_dir.mkdir(parents=True)
            # Write a package that raises on import
            pkg = adapters_dir / 'test_plugin_broken'
            pkg.mkdir()
            (pkg / '__init__.py').write_text('raise RuntimeError("intentional")\n')
            # Should not raise
            discover_adapter_plugins(cwd=Path(tmp))

    def test_dir_without_init_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapters_dir = Path(tmp) / '.reveal' / 'adapters'
            adapters_dir.mkdir(parents=True)
            (adapters_dir / 'not_a_package').mkdir()
            # No __init__.py — should skip silently
            discover_adapter_plugins(cwd=Path(tmp))

    def test_reset_allows_rediscovery(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            adapters_dir = Path(tmp_dir) / '.reveal' / 'adapters'
            adapters_dir.mkdir(parents=True)
            self._write_plugin(adapters_dir, 'test_plugin_reset')
            discover_adapter_plugins(cwd=Path(tmp_dir))
            self.assertIn('test_plugin_reset', _ADAPTER_REGISTRY)
            del _ADAPTER_REGISTRY['test_plugin_reset']
            for k in [k for k in sys.modules if k.startswith('reveal_plugin_adapter_test_plugin_reset')]:
                del sys.modules[k]
            _reset_adapter_plugin_discovery()
            discover_adapter_plugins(cwd=Path(tmp_dir))
            self.assertIn('test_plugin_reset', _ADAPTER_REGISTRY)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_plugin_scheme_returns_correct_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapters_dir = Path(tmp) / '.reveal' / 'adapters'
            adapters_dir.mkdir(parents=True)
            self._write_plugin(adapters_dir, 'test_plugin_class')
            discover_adapter_plugins(cwd=Path(tmp))
        cls = _ADAPTER_REGISTRY.get('test_plugin_class')
        self.assertIsNotNone(cls)
        self.assertTrue(issubclass(cls, __import__('reveal.adapters.base', fromlist=['ResourceAdapter']).ResourceAdapter))

    def test_unknown_scheme_still_returns_none(self):
        _reset_adapter_plugin_discovery()
        import unittest.mock as mock
        with mock.patch('pathlib.Path.cwd', return_value=Path('/nonexistent')):
            cls = get_adapter_class('test_plugin_definitely_not_registered_xyz')
        self.assertIsNone(cls)


if __name__ == '__main__':
    unittest.main()
