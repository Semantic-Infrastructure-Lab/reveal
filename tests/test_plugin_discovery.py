"""Tests for BACK-247: plugin auto-discovery via .reveal/analyzers/ and ~/.reveal/plugins/."""

import tempfile
import textwrap
import unittest
from pathlib import Path

from reveal.registry import (
    _ANALYZER_REGISTRY,
    _reset_plugin_discovery,
    discover_plugins,
    get_analyzer,
)


def _write_plugin(plugin_dir: Path, stem: str, extension: str) -> Path:
    """Write a minimal @register analyzer plugin file."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    content = textwrap.dedent(f"""\
        from reveal.base import FileAnalyzer
        from reveal.registry import register

        @register('{extension}', name='{stem}', icon='')
        class {stem}Analyzer(FileAnalyzer):
            def get_structure(self, **kwargs):
                return {{'type': '{stem}'}}
    """)
    path = plugin_dir / f'{stem.lower()}_analyzer.py'
    path.write_text(content)
    return path


class TestPluginDiscovery(unittest.TestCase):
    def setUp(self):
        _reset_plugin_discovery()
        self._original_registry = _ANALYZER_REGISTRY.copy()

    def tearDown(self):
        _reset_plugin_discovery()
        _ANALYZER_REGISTRY.clear()
        _ANALYZER_REGISTRY.update(self._original_registry)

    # --- basic discovery ---

    def test_project_local_plugin_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            _write_plugin(cwd / '.reveal' / 'analyzers', 'Testx', '.testx')
            discover_plugins(cwd=cwd)
            self.assertIsNotNone(get_analyzer('file.testx'))

    def test_plugin_analyzer_class_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            _write_plugin(cwd / '.reveal' / 'analyzers', 'Testy', '.testy')
            discover_plugins(cwd=cwd)
            cls = get_analyzer('file.testy')
            self.assertEqual(cls.type_name, 'Testy')

    def test_multiple_plugins_in_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plugin_dir = cwd / '.reveal' / 'analyzers'
            _write_plugin(plugin_dir, 'Aaaa', '.aaaa')
            _write_plugin(plugin_dir, 'Bbbb', '.bbbb')
            discover_plugins(cwd=cwd)
            self.assertIsNotNone(get_analyzer('file.aaaa'))
            self.assertIsNotNone(get_analyzer('file.bbbb'))

    # --- user-global dir ---

    def test_user_global_plugin_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_plugins = Path(tmp) / '.reveal' / 'plugins'
            _write_plugin(user_plugins, 'Glob', '.glob')
            # Patch Path.home() to return our temp dir
            import unittest.mock as mock
            with mock.patch('reveal.registry.Path') as MockPath:
                # Replicate real Path behaviour for everything except .home()
                real_path = Path

                def side_effect(arg='.', *a, **kw):
                    return real_path(arg, *a, **kw)

                MockPath.side_effect = side_effect
                MockPath.home.return_value = real_path(tmp)
                MockPath.cwd.return_value = real_path(tmp) / 'empty_cwd'
                _reset_plugin_discovery()
                discover_plugins(cwd=real_path(tmp) / 'empty_cwd')
            self.assertIsNotNone(_ANALYZER_REGISTRY.get('.glob'))

    # --- robustness ---

    def test_broken_plugin_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plugin_dir = cwd / '.reveal' / 'analyzers'
            plugin_dir.mkdir(parents=True)
            bad = plugin_dir / 'bad_analyzer.py'
            bad.write_text('this is not valid python !!!')
            # Must not raise
            discover_plugins(cwd=cwd)

    def test_non_matching_filename_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plugin_dir = cwd / '.reveal' / 'analyzers'
            plugin_dir.mkdir(parents=True)
            # Wrong naming convention — no _analyzer.py suffix
            (plugin_dir / 'myplugin.py').write_text(
                "from reveal.registry import register, _ANALYZER_REGISTRY\n"
                "_ANALYZER_REGISTRY['.nope'] = object\n"
            )
            discover_plugins(cwd=cwd)
            self.assertNotIn('.nope', _ANALYZER_REGISTRY)

    def test_missing_plugin_dirs_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            # Neither .reveal/analyzers nor any user dir exists
            discover_plugins(cwd=cwd)  # must not raise

    def test_empty_plugin_dir_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            (cwd / '.reveal' / 'analyzers').mkdir(parents=True)
            discover_plugins(cwd=cwd)  # must not raise

    # --- once-per-process guard ---

    def test_discovery_runs_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            _write_plugin(cwd / '.reveal' / 'analyzers', 'Once', '.once')
            discover_plugins(cwd=cwd)
            # Second discover with different cwd — first cwd should still win
            with tempfile.TemporaryDirectory() as tmp2:
                cwd2 = Path(tmp2)
                _write_plugin(cwd2 / '.reveal' / 'analyzers', 'Twice', '.twice')
                discover_plugins(cwd=cwd2)
                # .twice should NOT be loaded because discovery already ran
                self.assertNotIn('.twice', _ANALYZER_REGISTRY)

    def test_reset_allows_rediscovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            _write_plugin(cwd / '.reveal' / 'analyzers', 'Redo', '.redo')
            discover_plugins(cwd=cwd)
            _reset_plugin_discovery()
            _ANALYZER_REGISTRY.pop('.redo', None)
            # After reset, a fresh cwd discover should work
            with tempfile.TemporaryDirectory() as tmp2:
                cwd2 = Path(tmp2)
                _write_plugin(cwd2 / '.reveal' / 'analyzers', 'Fresh', '.fresh')
                discover_plugins(cwd=cwd2)
                self.assertIsNotNone(_ANALYZER_REGISTRY.get('.fresh'))

    # --- get_analyzer lazy trigger ---

    def test_get_analyzer_triggers_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            _write_plugin(cwd / '.reveal' / 'analyzers', 'Lazy', '.lazy')
            import unittest.mock as mock
            # Override Path.cwd() so get_analyzer picks up our temp cwd
            with mock.patch('reveal.registry.Path') as MockPath:
                real_path = Path

                def side_effect(arg='.', *a, **kw):
                    return real_path(arg, *a, **kw)

                MockPath.side_effect = side_effect
                MockPath.cwd.return_value = cwd
                MockPath.home.return_value = real_path.home()
                _reset_plugin_discovery()
                result = get_analyzer('file.lazy')
            self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
