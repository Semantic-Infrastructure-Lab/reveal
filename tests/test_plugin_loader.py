"""
Tests for plugin loader.

Tests YAML-based plugin loading and extension mapping.
"""

import tempfile
import unittest
from pathlib import Path
from reveal.plugin_loader import (
    PluginLoader,
    PluginDefinition,
    LevelDefinition,
    get_plugin_loader
)


class TestPluginDefinitionFromYAML(unittest.TestCase):
    """Test PluginDefinition creation from YAML data."""

    def test_parse_simple_plugin(self):
        """Should parse a simple plugin definition."""
        data = {
            "extension": ".txt",
            "name": "Text",
            "description": "Plain text files",
            "icon": "📄",
            "levels": {
                0: {
                    "name": "metadata",
                    "description": "File stats",
                    "breadcrumb": "Basic info",
                    "analyzer": None
                }
            }
        }

        plugin = PluginDefinition.from_yaml(data)

        self.assertEqual(plugin.extension, [".txt"])
        self.assertEqual(plugin.name, "Text")
        self.assertEqual(plugin.description, "Plain text files")
        self.assertEqual(plugin.icon, "📄")
        self.assertEqual(len(plugin.levels), 1)

    def test_parse_multiple_extensions(self):
        """Should handle multiple extensions as list."""
        data = {
            "extension": [".yaml", ".yml"],
            "name": "YAML",
            "description": "YAML files",
            "levels": {
                0: {
                    "name": "metadata",
                    "description": "Stats",
                    "breadcrumb": "Info",
                }
            }
        }

        plugin = PluginDefinition.from_yaml(data)

        self.assertEqual(plugin.extension, [".yaml", ".yml"])

    def test_parse_single_extension_as_string(self):
        """Should normalize single extension string to list."""
        data = {
            "extension": ".py",
            "name": "Python",
            "description": "Python files",
            "levels": {
                0: {
                    "name": "metadata",
                    "description": "Stats",
                    "breadcrumb": "Info",
                }
            }
        }

        plugin = PluginDefinition.from_yaml(data)

        self.assertEqual(plugin.extension, [".py"])

    def test_parse_level_with_all_fields(self):
        """Should parse level with all optional fields."""
        data = {
            "extension": ".py",
            "name": "Python",
            "description": "Python files",
            "levels": {
                1: {
                    "name": "structure",
                    "description": "Code structure",
                    "breadcrumb": "Classes and functions",
                    "analyzer": "python_structure",
                    "outputs": ["classes", "functions"],
                    "next_levels": [0, 2, 3],
                    "tips": ["Use --grep"],
                    "paging": True,
                    "page_size": 100
                }
            }
        }

        plugin = PluginDefinition.from_yaml(data)
        level = plugin.levels[1]

        self.assertEqual(level.name, "structure")
        self.assertEqual(level.analyzer, "python_structure")
        self.assertEqual(level.outputs, ["classes", "functions"])
        self.assertEqual(level.next_levels, [0, 2, 3])
        self.assertEqual(level.tips, ["Use --grep"])
        self.assertTrue(level.paging)
        self.assertEqual(level.page_size, 100)

    def test_parse_features(self):
        """Should parse features dictionary."""
        data = {
            "extension": ".py",
            "name": "Python",
            "description": "Python files",
            "levels": {
                0: {
                    "name": "metadata",
                    "description": "Stats",
                    "breadcrumb": "Info",
                }
            },
            "features": {
                "grep": True,
                "context": True,
                "paging": False
            }
        }

        plugin = PluginDefinition.from_yaml(data)

        self.assertTrue(plugin.features["grep"])
        self.assertTrue(plugin.features["context"])
        self.assertFalse(plugin.features["paging"])

    def test_parse_analyzer_config(self):
        """Should parse analyzer configuration."""
        data = {
            "extension": ".py",
            "name": "Python",
            "description": "Python files",
            "levels": {
                0: {
                    "name": "metadata",
                    "description": "Stats",
                    "breadcrumb": "Info",
                }
            },
            "analyzer_config": {
                "include_private": False,
                "parse_docstrings": True
            }
        }

        plugin = PluginDefinition.from_yaml(data)

        self.assertFalse(plugin.analyzer_config["include_private"])
        self.assertTrue(plugin.analyzer_config["parse_docstrings"])

    def test_parse_examples(self):
        """Should parse example commands."""
        data = {
            "extension": ".py",
            "name": "Python",
            "description": "Python files",
            "levels": {
                0: {
                    "name": "metadata",
                    "description": "Stats",
                    "breadcrumb": "Info",
                }
            },
            "examples": [
                {"command": "reveal file.py", "description": "Show metadata"},
                {"command": "reveal file.py -l 1", "description": "Show structure"}
            ]
        }

        plugin = PluginDefinition.from_yaml(data)

        self.assertEqual(len(plugin.examples), 2)
        self.assertEqual(plugin.examples[0]["command"], "reveal file.py")

    def test_default_icon(self):
        """Should use default icon if not specified."""
        data = {
            "extension": ".txt",
            "name": "Text",
            "description": "Plain text",
            "levels": {
                0: {
                    "name": "metadata",
                    "description": "Stats",
                    "breadcrumb": "Info",
                }
            }
        }

        plugin = PluginDefinition.from_yaml(data)

        self.assertEqual(plugin.icon, "📄")


class TestPluginLoader(unittest.TestCase):
    """Test PluginLoader functionality."""

    def setUp(self):
        """Create temporary plugin directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.plugin_dir = Path(self.temp_dir)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def create_test_plugin(self, filename, content):
        """Helper to create a test plugin file."""
        plugin_file = self.plugin_dir / filename
        with open(plugin_file, 'w') as f:
            f.write(content)
        return plugin_file

    def test_load_single_plugin(self):
        """Should load a single plugin from YAML."""
        yaml_content = """
extension: .test
name: Test
description: Test plugin
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        self.create_test_plugin("test.yaml", yaml_content)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        self.assertIn("Test", loader.list_plugins())
        self.assertIn(".test", loader.get_supported_extensions())

    def test_load_multiple_plugins(self):
        """Should load multiple plugins from directory."""
        yaml1 = """
extension: .test1
name: Test1
description: First test plugin
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        yaml2 = """
extension: .test2
name: Test2
description: Second test plugin
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        self.create_test_plugin("test1.yaml", yaml1)
        self.create_test_plugin("test2.yaml", yaml2)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        self.assertIn("Test1", loader.list_plugins())
        self.assertIn("Test2", loader.list_plugins())

    def test_get_plugin_for_file(self):
        """Should retrieve plugin based on file extension."""
        yaml_content = """
extension: [.py, .pyx]
name: Python
description: Python files
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        self.create_test_plugin("python.yaml", yaml_content)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        plugin = loader.get_plugin_for_file("script.py")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "Python")

        plugin2 = loader.get_plugin_for_file("module.pyx")
        self.assertIsNotNone(plugin2)
        self.assertEqual(plugin2.name, "Python")

    def test_get_plugin_for_unknown_extension(self):
        """Should return None for unknown extensions."""
        yaml_content = """
extension: .py
name: Python
description: Python files
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        self.create_test_plugin("python.yaml", yaml_content)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        plugin = loader.get_plugin_for_file("unknown.xyz")
        self.assertIsNone(plugin)

    def test_get_plugin_by_name(self):
        """Should retrieve plugin by name."""
        yaml_content = """
extension: .test
name: TestPlugin
description: Test plugin
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        self.create_test_plugin("test.yaml", yaml_content)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        plugin = loader.get_plugin_by_name("TestPlugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "TestPlugin")

        unknown = loader.get_plugin_by_name("NonExistent")
        self.assertIsNone(unknown)

    def test_list_plugins(self):
        """Should list all loaded plugin names."""
        yaml1 = """
extension: .test1
name: Plugin1
description: First
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        yaml2 = """
extension: .test2
name: Plugin2
description: Second
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        self.create_test_plugin("p1.yaml", yaml1)
        self.create_test_plugin("p2.yaml", yaml2)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        plugins = loader.list_plugins()
        self.assertIn("Plugin1", plugins)
        self.assertIn("Plugin2", plugins)

    def test_get_supported_extensions(self):
        """Should return sorted list of supported extensions."""
        yaml_content = """
extension: [.py, .pyx, .pyi]
name: Python
description: Python files
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        self.create_test_plugin("python.yaml", yaml_content)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        extensions = loader.get_supported_extensions()
        self.assertIn(".py", extensions)
        self.assertIn(".pyx", extensions)
        self.assertIn(".pyi", extensions)
        # Should be sorted
        self.assertEqual(extensions, sorted(extensions))

    def test_get_level_info(self):
        """Should retrieve level information for a file."""
        yaml_content = """
extension: .test
name: Test
description: Test plugin
levels:
  0:
    name: metadata
    description: File stats
    breadcrumb: Basic info
  1:
    name: structure
    description: Code structure
    breadcrumb: Classes and functions
"""
        self.create_test_plugin("test.yaml", yaml_content)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        level0 = loader.get_level_info("file.test", 0)
        self.assertIsNotNone(level0)
        self.assertEqual(level0.name, "metadata")

        level1 = loader.get_level_info("file.test", 1)
        self.assertIsNotNone(level1)
        self.assertEqual(level1.name, "structure")

        level99 = loader.get_level_info("file.test", 99)
        self.assertIsNone(level99)

    def test_get_breadcrumbs(self):
        """Should generate breadcrumb navigation hints."""
        yaml_content = """
extension: .test
name: Test
description: Test plugin
levels:
  0:
    name: metadata
    description: File stats
    breadcrumb: Basic info
    next_levels: [1, 2]
  1:
    name: structure
    description: Code structure
    breadcrumb: Classes and functions
    next_levels: [0, 2]
  2:
    name: full
    description: Full content
    breadcrumb: Complete file
    next_levels: [0, 1]
"""
        self.create_test_plugin("test.yaml", yaml_content)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        breadcrumbs = loader.get_breadcrumbs("file.test", 0)
        self.assertGreater(len(breadcrumbs), 0)
        # Should contain references to next levels
        breadcrumb_text = '\n'.join(breadcrumbs)
        self.assertIn("--level 1", breadcrumb_text)
        self.assertIn("--level 2", breadcrumb_text)

    def test_skip_invalid_yaml(self):
        """Should skip invalid YAML files and continue loading."""
        # Create invalid YAML
        invalid_yaml = "{ invalid yaml content : ["
        self.create_test_plugin("invalid.yaml", invalid_yaml)

        # Create valid YAML
        valid_yaml = """
extension: .test
name: Valid
description: Valid plugin
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        self.create_test_plugin("valid.yaml", valid_yaml)

        # Should not crash, should load valid plugin
        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        # Valid plugin should be loaded
        self.assertIn("Valid", loader.list_plugins())

    def test_nonexistent_plugin_directory(self):
        """Should handle nonexistent plugin directories gracefully."""
        fake_dir = Path("/tmp/nonexistent_plugin_dir_12345")

        # Should not crash
        loader = PluginLoader(plugin_dirs=[fake_dir])

        # Should have no plugins loaded
        self.assertEqual(len(loader.list_plugins()), 0)

    def test_case_insensitive_extension_lookup(self):
        """Should match extensions case-insensitively."""
        yaml_content = """
extension: .test
name: Test
description: Test plugin
levels:
  0:
    name: metadata
    description: Stats
    breadcrumb: Info
"""
        self.create_test_plugin("test.yaml", yaml_content)

        loader = PluginLoader(plugin_dirs=[self.plugin_dir])

        # Should find plugin regardless of case
        plugin1 = loader.get_plugin_for_file("file.test")
        plugin2 = loader.get_plugin_for_file("file.TEST")
        plugin3 = loader.get_plugin_for_file("file.Test")

        self.assertIsNotNone(plugin1)
        self.assertIsNotNone(plugin2)
        self.assertIsNotNone(plugin3)


class TestGetPluginLoader(unittest.TestCase):
    """Test global plugin loader singleton."""

    def test_get_plugin_loader_returns_instance(self):
        """Should return a PluginLoader instance."""
        loader = get_plugin_loader()
        self.assertIsInstance(loader, PluginLoader)

    def test_get_plugin_loader_singleton(self):
        """Should return the same instance on multiple calls."""
        loader1 = get_plugin_loader()
        loader2 = get_plugin_loader()
        self.assertIs(loader1, loader2)


if __name__ == '__main__':
    unittest.main()
