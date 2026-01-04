"""Comprehensive tests for reveal configuration system.

Tests cover:
- Deep merge algorithm
- Multi-level precedence (CLI, env, project, user, system)
- Directory walk-up discovery
- Schema validation
- Rule configuration
- File-specific overrides
- Ignore patterns
- Backwards compatibility
"""

import unittest
import tempfile
import os
import shutil
from pathlib import Path
from typing import Dict, Any
import yaml

from reveal.config import (
    RevealConfig,
    deep_merge,
    load_config,
    get_config,
    FileConfig,
    Override,
    CONFIG_SCHEMA
)


class TestDeepMerge(unittest.TestCase):
    """Test deep merge algorithm with various data types."""

    def test_scalar_override(self):
        """Test scalars are replaced by override."""
        base = {'threshold': 10, 'enabled': True, 'name': 'base'}
        override = {'threshold': 15, 'enabled': False}

        result = deep_merge(base, override)

        self.assertEqual(result['threshold'], 15)
        self.assertEqual(result['enabled'], False)
        self.assertEqual(result['name'], 'base')  # Not in override

    def test_list_concatenation(self):
        """Test lists are concatenated (extended)."""
        base = {'disable': ['E501', 'D001']}
        override = {'disable': ['B001', 'S701']}

        result = deep_merge(base, override)

        self.assertEqual(result['disable'], ['E501', 'D001', 'B001', 'S701'])

    def test_empty_list_handling(self):
        """Test empty list handling."""
        base = {'disable': ['E501']}
        override = {'disable': []}

        result = deep_merge(base, override)

        self.assertEqual(result['disable'], ['E501'])  # Empty list extends

    def test_dict_recursive_merge(self):
        """Test nested dicts are merged recursively."""
        base = {
            'rules': {
                'C901': {'threshold': 10},
                'E501': {'max_length': 100}
            }
        }
        override = {
            'rules': {
                'C901': {'threshold': 15},  # Override
                'B001': {'enabled': False}  # New rule
            }
        }

        result = deep_merge(base, override)

        self.assertEqual(result['rules']['C901']['threshold'], 15)
        self.assertEqual(result['rules']['E501']['max_length'], 100)  # Preserved
        self.assertEqual(result['rules']['B001']['enabled'], False)

    def test_type_mismatch_override_wins(self):
        """Test that when types mismatch, override wins."""
        base = {'value': ['list', 'of', 'items']}
        override = {'value': 'scalar_string'}

        result = deep_merge(base, override)

        self.assertEqual(result['value'], 'scalar_string')

    def test_deep_nested_merge(self):
        """Test deeply nested structures merge correctly."""
        base = {
            'level1': {
                'level2': {
                    'level3': {
                        'value': 'old',
                        'keep': True
                    }
                }
            }
        }
        override = {
            'level1': {
                'level2': {
                    'level3': {
                        'value': 'new'
                    }
                }
            }
        }

        result = deep_merge(base, override)

        self.assertEqual(result['level1']['level2']['level3']['value'], 'new')
        self.assertTrue(result['level1']['level2']['level3']['keep'])

    def test_new_keys_added(self):
        """Test that new keys from override are added."""
        base = {'existing': 'value'}
        override = {'new_key': 'new_value', 'another': 123}

        result = deep_merge(base, override)

        self.assertEqual(result['existing'], 'value')
        self.assertEqual(result['new_key'], 'new_value')
        self.assertEqual(result['another'], 123)

    def test_empty_dicts(self):
        """Test merge with empty dicts."""
        self.assertEqual(deep_merge({}, {}), {})
        self.assertEqual(deep_merge({'a': 1}, {}), {'a': 1})
        self.assertEqual(deep_merge({}, {'b': 2}), {'b': 2})

    def test_complex_real_world_example(self):
        """Test complex real-world configuration merge."""
        base = {
            'ignore': ['*.pyc', '__pycache__'],
            'rules': {
                'disable': ['E501'],
                'C901': {'threshold': 10},
                'E501': {'max_length': 100, 'ignore_urls': False}
            },
            'architecture': {
                'layers': [
                    {'name': 'api', 'paths': ['api/**']}
                ]
            }
        }

        override = {
            'ignore': ['build/', 'dist/'],
            'rules': {
                'disable': ['D001'],
                'C901': {'threshold': 15},
                'E501': {'ignore_urls': True}
            },
            'architecture': {
                'layers': [
                    {'name': 'core', 'paths': ['core/**']}
                ]
            }
        }

        result = deep_merge(base, override)

        # Lists concatenated
        self.assertEqual(result['ignore'],
                        ['*.pyc', '__pycache__', 'build/', 'dist/'])
        self.assertEqual(result['rules']['disable'], ['E501', 'D001'])
        self.assertEqual(len(result['architecture']['layers']), 2)

        # Dicts merged
        self.assertEqual(result['rules']['C901']['threshold'], 15)
        self.assertEqual(result['rules']['E501']['max_length'], 100)
        self.assertEqual(result['rules']['E501']['ignore_urls'], True)


class TestConfigLoading(unittest.TestCase):
    """Test configuration loading from files."""

    def setUp(self):
        """Create temporary directory for test configs."""
        self.temp_dir = tempfile.mkdtemp()
        # Clear cache before each test
        RevealConfig._cache.clear()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        RevealConfig._cache.clear()

    def write_config(self, path: Path, config: Dict[str, Any]):
        """Helper: Write YAML config to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump(config, f)

    def test_load_single_config(self):
        """Test loading a single .reveal.yaml file."""
        config_path = Path(self.temp_dir) / '.reveal.yaml'
        config_data = {
            'root': True,
            'rules': {
                'disable': ['E501']
            }
        }
        self.write_config(config_path, config_data)

        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertEqual(cfg._config['rules']['disable'], ['E501'])

    def test_no_config_mode(self):
        """Test no_config flag uses only defaults."""
        config_path = Path(self.temp_dir) / '.reveal.yaml'
        config_data = {'rules': {'disable': ['E501']}}
        self.write_config(config_path, config_data)

        cfg = RevealConfig.get(Path(self.temp_dir), no_config=True)

        # Should not have loaded the config file
        self.assertNotIn('disable', cfg._config.get('rules', {}))

    def test_cli_overrides_highest_precedence(self):
        """Test CLI overrides have highest precedence."""
        config_path = Path(self.temp_dir) / '.reveal.yaml'
        config_data = {
            'root': True,
            'rules': {
                'C901': {'threshold': 10}
            }
        }
        self.write_config(config_path, config_data)

        cli_overrides = {
            'rules': {
                'C901': {'threshold': 20}
            }
        }

        cfg = RevealConfig.get(Path(self.temp_dir), cli_overrides=cli_overrides)

        self.assertEqual(cfg.get_rule_config('C901', 'threshold'), 20)

    def test_caching_same_project_root(self):
        """Test config is cached per project root."""
        config_path = Path(self.temp_dir) / '.reveal.yaml'
        config_data = {'root': True, 'rules': {'disable': ['E501']}}
        self.write_config(config_path, config_data)

        cfg1 = RevealConfig.get(Path(self.temp_dir))
        cfg2 = RevealConfig.get(Path(self.temp_dir))

        # Should return same cached instance
        self.assertIs(cfg1, cfg2)


class TestDirectoryWalkUp(unittest.TestCase):
    """Test directory walk-up discovery."""

    def setUp(self):
        """Create nested directory structure."""
        self.temp_dir = tempfile.mkdtemp()
        RevealConfig._cache.clear()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        RevealConfig._cache.clear()

    def write_config(self, path: Path, config: Dict[str, Any]):
        """Helper: Write YAML config."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump(config, f)

    def test_finds_config_in_parent(self):
        """Test config discovery walks up to parent directories."""
        # Create nested structure: temp_dir/project/src/module/
        project_dir = Path(self.temp_dir) / 'project'
        module_dir = project_dir / 'src' / 'module'
        module_dir.mkdir(parents=True, exist_ok=True)

        # Put config at project root
        config_path = project_dir / '.reveal.yaml'
        config_data = {
            'root': True,
            'rules': {'disable': ['E501']}
        }
        self.write_config(config_path, config_data)

        # Load from nested directory
        cfg = RevealConfig.get(module_dir)

        self.assertEqual(cfg._config['rules']['disable'], ['E501'])
        self.assertEqual(cfg.project_root, project_dir.resolve())

    def test_stops_at_root_marker(self):
        """Test discovery stops at root: true marker."""
        # Create: temp_dir/outer/inner/
        outer_dir = Path(self.temp_dir) / 'outer'
        inner_dir = outer_dir / 'inner'
        inner_dir.mkdir(parents=True, exist_ok=True)

        # Outer config (should not be found)
        outer_config = outer_dir / '.reveal.yaml'
        self.write_config(outer_config, {
            'rules': {'disable': ['OUTER']}
        })

        # Inner config with root: true
        inner_config = inner_dir / '.reveal.yaml'
        self.write_config(inner_config, {
            'root': True,
            'rules': {'disable': ['INNER']}
        })

        cfg = RevealConfig.get(inner_dir)

        # Should only find inner config
        self.assertEqual(cfg._config['rules']['disable'], ['INNER'])
        self.assertNotIn('OUTER', cfg._config['rules']['disable'])

    def test_merges_multiple_configs(self):
        """Test multiple configs are merged with correct precedence."""
        # Create: temp_dir/project/src/
        project_dir = Path(self.temp_dir) / 'project'
        src_dir = project_dir / 'src'
        src_dir.mkdir(parents=True, exist_ok=True)

        # Project config (base)
        project_config = project_dir / '.reveal.yaml'
        self.write_config(project_config, {
            'root': True,
            'rules': {
                'disable': ['E501'],
                'C901': {'threshold': 10}
            }
        })

        # Src config (override - no root: true, so both should merge)
        src_config = src_dir / '.reveal.yaml'
        self.write_config(src_config, {
            'rules': {
                'disable': ['D001'],
                'C901': {'threshold': 15}
            }
        })

        cfg = RevealConfig.get(src_dir)

        # Lists should concatenate
        self.assertIn('E501', cfg._config['rules']['disable'])
        self.assertIn('D001', cfg._config['rules']['disable'])

        # Nearest (src) should override
        self.assertEqual(cfg.get_rule_config('C901', 'threshold'), 15)


class TestRuleConfiguration(unittest.TestCase):
    """Test rule-specific configuration."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        RevealConfig._cache.clear()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        RevealConfig._cache.clear()

    def write_config(self, config: Dict[str, Any]):
        """Helper: Write config to temp dir."""
        path = Path(self.temp_dir) / '.reveal.yaml'
        with open(path, 'w') as f:
            yaml.dump(config, f)

    def test_is_rule_enabled_default(self):
        """Test rules are enabled by default."""
        self.write_config({'root': True})
        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertTrue(cfg.is_rule_enabled('E501'))
        self.assertTrue(cfg.is_rule_enabled('C901'))

    def test_is_rule_disabled_explicit(self):
        """Test explicitly disabled rules."""
        self.write_config({
            'root': True,
            'rules': {
                'disable': ['E501', 'D001']
            }
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertFalse(cfg.is_rule_enabled('E501'))
        self.assertFalse(cfg.is_rule_enabled('D001'))
        self.assertTrue(cfg.is_rule_enabled('C901'))

    def test_select_category(self):
        """Test selecting specific rule categories."""
        self.write_config({
            'root': True,
            'rules': {
                'select': ['B', 'S']  # Only bugs and security
            }
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertTrue(cfg.is_rule_enabled('B001'))
        self.assertTrue(cfg.is_rule_enabled('S701'))
        self.assertFalse(cfg.is_rule_enabled('E501'))
        self.assertFalse(cfg.is_rule_enabled('C901'))

    def test_select_specific_rule(self):
        """Test selecting specific individual rules."""
        self.write_config({
            'root': True,
            'rules': {
                'select': ['E501', 'C901']
            }
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertTrue(cfg.is_rule_enabled('E501'))
        self.assertTrue(cfg.is_rule_enabled('C901'))
        self.assertFalse(cfg.is_rule_enabled('E502'))

    def test_get_rule_config_value(self):
        """Test getting rule-specific config values."""
        self.write_config({
            'root': True,
            'rules': {
                'C901': {'threshold': 15},
                'E501': {'max_length': 120, 'ignore_urls': True}
            }
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertEqual(cfg.get_rule_config('C901', 'threshold'), 15)
        self.assertEqual(cfg.get_rule_config('E501', 'max_length'), 120)
        self.assertTrue(cfg.get_rule_config('E501', 'ignore_urls'))

    def test_get_rule_config_default(self):
        """Test default values when config not present."""
        self.write_config({'root': True})
        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertEqual(cfg.get_rule_config('C901', 'threshold', 10), 10)
        self.assertIsNone(cfg.get_rule_config('C901', 'threshold'))

    def test_rules_globally_disabled(self):
        """Test disabling all rules globally."""
        self.write_config({
            'root': True,
            'rules': {
                'enabled': False
            }
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertFalse(cfg.is_rule_enabled('E501'))
        self.assertFalse(cfg.is_rule_enabled('C901'))


class TestFileOverrides(unittest.TestCase):
    """Test per-file/directory configuration overrides."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        RevealConfig._cache.clear()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        RevealConfig._cache.clear()

    def write_config(self, config: Dict[str, Any]):
        """Helper: Write config."""
        path = Path(self.temp_dir) / '.reveal.yaml'
        with open(path, 'w') as f:
            yaml.dump(config, f)

    def test_override_matches_pattern(self):
        """Test Override.matches() with file patterns."""
        # Test pattern matching with tests/**
        override = Override(
            files_pattern='tests/**',
            config={}
        )

        project_root = Path(self.temp_dir)

        # Should match any file under tests/
        self.assertTrue(override.matches(
            Path(self.temp_dir) / 'tests' / 'test_foo.py',
            project_root
        ))
        self.assertTrue(override.matches(
            Path(self.temp_dir) / 'tests' / 'unit' / 'test_bar.py',
            project_root
        ))
        # Should not match files outside tests/
        self.assertFalse(override.matches(
            Path(self.temp_dir) / 'src' / 'main.py',
            project_root
        ))

        # Test pattern with **.py - matches .py files at any depth
        override2 = Override(
            files_pattern='tests/**/*.py',
            config={}
        )
        # ** matches zero or more directories, so both should match
        self.assertTrue(override2.matches(
            Path(self.temp_dir) / 'tests' / 'test_foo.py',
            project_root
        ))
        self.assertTrue(override2.matches(
            Path(self.temp_dir) / 'tests' / 'unit' / 'test_bar.py',
            project_root
        ))

    def test_file_config_applies_overrides(self):
        """Test FileConfig applies matching overrides."""
        self.write_config({
            'root': True,
            'rules': {
                'C901': {'threshold': 10}
            },
            'overrides': [
                {
                    'files': 'tests/**',
                    'rules': {
                        'C901': {'threshold': 20}  # Higher threshold for tests
                    }
                }
            ]
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        # Regular file uses base config
        regular_file = Path(self.temp_dir) / 'src' / 'main.py'
        regular_config = cfg.get_file_config(regular_file)
        self.assertEqual(
            regular_config.get_rule_config('C901', 'threshold'),
            10
        )

        # Test file uses override
        test_file = Path(self.temp_dir) / 'tests' / 'test_main.py'
        test_config = cfg.get_file_config(test_file)
        self.assertEqual(
            test_config.get_rule_config('C901', 'threshold'),
            20
        )

    def test_multiple_overrides_applied(self):
        """Test multiple matching overrides are applied in order."""
        self.write_config({
            'root': True,
            'rules': {
                'disable': []
            },
            'overrides': [
                {
                    'files': 'tests/**',
                    'rules': {'disable': ['C901']}
                },
                {
                    'files': 'tests/integration/**',
                    'rules': {'disable': ['E501']}
                }
            ]
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        # Integration test gets both overrides
        integration_file = Path(self.temp_dir) / 'tests' / 'integration' / 'test_api.py'
        integration_config = cfg.get_file_config(integration_file)

        disabled = integration_config._config['rules']['disable']
        self.assertIn('C901', disabled)
        self.assertIn('E501', disabled)

    def test_file_config_is_rule_enabled(self):
        """Test FileConfig.is_rule_enabled() respects overrides."""
        self.write_config({
            'root': True,
            'overrides': [
                {
                    'files': 'scripts/**',
                    'rules': {'disable': ['E501', 'D001']}
                }
            ]
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        script_file = Path(self.temp_dir) / 'scripts' / 'deploy.py'
        script_config = cfg.get_file_config(script_file)

        self.assertFalse(script_config.is_rule_enabled('E501'))
        self.assertFalse(script_config.is_rule_enabled('D001'))
        self.assertTrue(script_config.is_rule_enabled('C901'))


class TestIgnorePatterns(unittest.TestCase):
    """Test file ignore patterns."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        RevealConfig._cache.clear()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        RevealConfig._cache.clear()

    def write_config(self, config: Dict[str, Any]):
        """Helper: Write config."""
        path = Path(self.temp_dir) / '.reveal.yaml'
        with open(path, 'w') as f:
            yaml.dump(config, f)

    def test_should_ignore_matches_pattern(self):
        """Test should_ignore() matches patterns."""
        self.write_config({
            'root': True,
            'ignore': [
                '*.pyc',
                '__pycache__/**',
                'build/**',
                'dist/**'
            ]
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertTrue(cfg.should_ignore(Path('module.pyc')))
        self.assertTrue(cfg.should_ignore(Path('__pycache__/foo.pyc')))
        self.assertTrue(cfg.should_ignore(Path('build/lib/module.py')))
        self.assertTrue(cfg.should_ignore(Path('dist/package.tar.gz')))

    def test_should_ignore_no_match(self):
        """Test should_ignore() returns False when no match."""
        self.write_config({
            'root': True,
            'ignore': ['*.pyc', 'build/**']
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        self.assertFalse(cfg.should_ignore(Path('src/main.py')))
        self.assertFalse(cfg.should_ignore(Path('tests/test_foo.py')))

    def test_ignore_with_relative_paths(self):
        """Test ignore patterns work with relative paths."""
        self.write_config({
            'root': True,
            'ignore': ['tests/**']
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        # Relative to project root
        test_file = Path(self.temp_dir) / 'tests' / 'test_foo.py'
        self.assertTrue(cfg.should_ignore(test_file))


class TestLayersAndAdapters(unittest.TestCase):
    """Test architecture layers and adapter configuration."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        RevealConfig._cache.clear()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        RevealConfig._cache.clear()

    def write_config(self, config: Dict[str, Any]):
        """Helper: Write config."""
        path = Path(self.temp_dir) / '.reveal.yaml'
        with open(path, 'w') as f:
            yaml.dump(config, f)

    def test_get_layers_configuration(self):
        """Test get_layers() returns architecture layers."""
        self.write_config({
            'root': True,
            'architecture': {
                'layers': [
                    {
                        'name': 'api',
                        'paths': ['api/**'],
                        'allow_imports': ['core/**']
                    },
                    {
                        'name': 'core',
                        'paths': ['core/**'],
                        'deny_imports': ['api/**']
                    }
                ]
            }
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        layers = cfg.get_layers()
        self.assertEqual(len(layers), 2)
        self.assertEqual(layers[0]['name'], 'api')
        self.assertEqual(layers[1]['name'], 'core')

    def test_get_layers_empty(self):
        """Test get_layers() when no layers defined."""
        self.write_config({'root': True})
        cfg = RevealConfig.get(Path(self.temp_dir))

        layers = cfg.get_layers()
        self.assertEqual(layers, [])

    def test_get_adapter_config(self):
        """Test adapter-specific configuration."""
        self.write_config({
            'root': True,
            'adapters': {
                'mysql': {
                    'health_checks': {
                        'max_connections': 100
                    },
                    'timeout': 30
                }
            }
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        mysql_config = cfg.get_adapter_config('mysql')
        self.assertEqual(mysql_config['timeout'], 30)

        health_config = cfg.get_adapter_config('mysql', 'health_checks')
        self.assertEqual(health_config['max_connections'], 100)

    def test_get_plugin_config(self):
        """Test plugin namespace isolation."""
        self.write_config({
            'root': True,
            'plugins': {
                'my-plugin': {
                    'enabled': True,
                    'option': 'value'
                }
            }
        })
        cfg = RevealConfig.get(Path(self.temp_dir))

        plugin_config = cfg.get_plugin_config('my-plugin')
        self.assertTrue(plugin_config['enabled'])
        self.assertEqual(plugin_config['option'], 'value')

    def test_get_plugin_config_missing(self):
        """Test get_plugin_config() returns empty dict when missing."""
        self.write_config({'root': True})
        cfg = RevealConfig.get(Path(self.temp_dir))

        plugin_config = cfg.get_plugin_config('nonexistent')
        self.assertEqual(plugin_config, {})


class TestBackwardsCompatibility(unittest.TestCase):
    """Test backwards compatibility with legacy config system."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        RevealConfig._cache.clear()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        RevealConfig._cache.clear()

    def test_load_config_function_exists(self):
        """Test deprecated load_config() function still works."""
        # Create legacy config location
        config_dir = Path(self.temp_dir) / '.reveal'
        config_dir.mkdir(parents=True)
        config_path = config_dir / 'test-config.yaml'

        with open(config_path, 'w') as f:
            yaml.dump({'test': 'value'}, f)

        # Change to temp dir so load_config can find it
        old_cwd = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            result = load_config('test-config.yaml', default={})
            self.assertEqual(result.get('test'), 'value')
        finally:
            os.chdir(old_cwd)

    def test_get_config_global_function(self):
        """Test global get_config() convenience function."""
        config_path = Path(self.temp_dir) / '.reveal.yaml'
        with open(config_path, 'w') as f:
            yaml.dump({'root': True, 'test': 'global'}, f)

        cfg = get_config(Path(self.temp_dir))
        self.assertEqual(cfg._config.get('test'), 'global')

    def test_user_data_dir_property(self):
        """Test user_data_dir property for backwards compat."""
        config_path = Path(self.temp_dir) / '.reveal.yaml'
        with open(config_path, 'w') as f:
            yaml.dump({'root': True}, f)

        cfg = RevealConfig.get(Path(self.temp_dir))

        # Should return a Path object
        self.assertIsInstance(cfg.user_data_dir, Path)


class TestEnvironmentVariables(unittest.TestCase):
    """Test environment variable configuration."""

    def setUp(self):
        """Save original environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_env = os.environ.copy()
        RevealConfig._cache.clear()

    def tearDown(self):
        """Restore environment and clean up."""
        os.environ.clear()
        os.environ.update(self.old_env)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        RevealConfig._cache.clear()

    def write_config(self, config: Dict[str, Any]):
        """Write config to temp directory."""
        config_path = Path(self.temp_dir) / '.reveal.yaml'
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

    def test_reveal_rules_disable(self):
        """Test REVEAL_RULES_DISABLE environment variable."""
        self.write_config({'root': True, 'rules': {'disable': ['E501']}})

        os.environ['REVEAL_RULES_DISABLE'] = 'C901,D001'
        cfg = RevealConfig.get(Path(self.temp_dir))

        # Env var should override file config (env has higher precedence)
        disabled = cfg._config.get('rules', {}).get('disable', [])
        self.assertIn('C901', disabled)
        self.assertIn('D001', disabled)

    def test_reveal_rules_select(self):
        """Test REVEAL_RULES_SELECT environment variable."""
        os.environ['REVEAL_RULES_SELECT'] = 'B,S'
        cfg = RevealConfig.get(Path(self.temp_dir))

        selected = cfg._config.get('rules', {}).get('select', [])
        self.assertIn('B', selected)
        self.assertIn('S', selected)

    def test_reveal_format(self):
        """Test REVEAL_FORMAT environment variable."""
        os.environ['REVEAL_FORMAT'] = 'json'
        cfg = RevealConfig.get(Path(self.temp_dir))

        fmt = cfg._config.get('output', {}).get('format')
        self.assertEqual(fmt, 'json')

    def test_reveal_ignore(self):
        """Test REVEAL_IGNORE environment variable."""
        os.environ['REVEAL_IGNORE'] = '*.min.js,vendor/**'
        cfg = RevealConfig.get(Path(self.temp_dir))

        ignore = cfg._config.get('ignore', [])
        self.assertIn('*.min.js', ignore)
        self.assertIn('vendor/**', ignore)

    def test_reveal_c901_threshold(self):
        """Test REVEAL_C901_THRESHOLD environment variable."""
        os.environ['REVEAL_C901_THRESHOLD'] = '20'
        cfg = RevealConfig.get(Path(self.temp_dir))

        threshold = cfg._config.get('rules', {}).get('C901', {}).get('threshold')
        self.assertEqual(threshold, 20)

    def test_reveal_e501_max_length(self):
        """Test REVEAL_E501_MAX_LENGTH environment variable."""
        os.environ['REVEAL_E501_MAX_LENGTH'] = '120'
        cfg = RevealConfig.get(Path(self.temp_dir))

        max_length = cfg._config.get('rules', {}).get('E501', {}).get('max_length')
        self.assertEqual(max_length, 120)

    def test_reveal_no_config(self):
        """Test REVEAL_NO_CONFIG environment variable."""
        self.write_config({'root': True, 'rules': {'disable': ['E501']}})

        os.environ['REVEAL_NO_CONFIG'] = '1'
        cfg = RevealConfig.get(Path(self.temp_dir))

        # Config file should be ignored
        disabled = cfg._config.get('rules', {}).get('disable', [])
        self.assertEqual(len(disabled), 0)

    def test_reveal_config_custom_file(self):
        """Test REVEAL_CONFIG environment variable for custom config file."""
        # Create custom config in different location
        custom_config = Path(self.temp_dir) / 'custom.yaml'
        with open(custom_config, 'w') as f:
            yaml.dump({
                'rules': {'disable': ['CUSTOM1', 'CUSTOM2']}
            }, f)

        # Create default config that should be ignored
        self.write_config({'root': True, 'rules': {'disable': ['E501']}})

        os.environ['REVEAL_CONFIG'] = str(custom_config)
        cfg = RevealConfig.get(Path(self.temp_dir))

        # Should load custom config instead of project config
        disabled = cfg._config.get('rules', {}).get('disable', [])
        self.assertIn('CUSTOM1', disabled)
        self.assertIn('CUSTOM2', disabled)
        # E501 should not be present (from ignored project config)
        self.assertNotIn('E501', disabled)

    def test_env_vars_override_file_config(self):
        """Test that environment variables have higher precedence than file configs."""
        self.write_config({
            'root': True,
            'rules': {
                'disable': ['E501'],
                'C901': {'threshold': 10}
            }
        })

        os.environ['REVEAL_C901_THRESHOLD'] = '25'
        cfg = RevealConfig.get(Path(self.temp_dir))

        # Env var should override file config
        threshold = cfg._config.get('rules', {}).get('C901', {}).get('threshold')
        self.assertEqual(threshold, 25)

    def test_multiple_env_vars_combined(self):
        """Test multiple environment variables work together."""
        os.environ['REVEAL_RULES_DISABLE'] = 'E501,D001'
        os.environ['REVEAL_RULES_SELECT'] = 'B'
        os.environ['REVEAL_FORMAT'] = 'json'
        os.environ['REVEAL_IGNORE'] = '*.min.js'
        os.environ['REVEAL_C901_THRESHOLD'] = '15'

        cfg = RevealConfig.get(Path(self.temp_dir))

        # All env vars should be applied
        self.assertIn('E501', cfg._config.get('rules', {}).get('disable', []))
        self.assertIn('B', cfg._config.get('rules', {}).get('select', []))
        self.assertEqual(cfg._config.get('output', {}).get('format'), 'json')
        self.assertIn('*.min.js', cfg._config.get('ignore', []))
        self.assertEqual(cfg._config.get('rules', {}).get('C901', {}).get('threshold'), 15)

    def test_invalid_threshold_value(self):
        """Test invalid threshold value is handled gracefully."""
        os.environ['REVEAL_C901_THRESHOLD'] = 'not-a-number'
        cfg = RevealConfig.get(Path(self.temp_dir))

        # Should not crash, threshold should not be set
        threshold = cfg._config.get('rules', {}).get('C901', {}).get('threshold')
        self.assertIsNone(threshold)


class TestConfigDump(unittest.TestCase):
    """Test configuration debugging/introspection."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        RevealConfig._cache.clear()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        RevealConfig._cache.clear()

    def test_dump_returns_yaml_string(self):
        """Test dump() returns YAML representation."""
        config_path = Path(self.temp_dir) / '.reveal.yaml'
        with open(config_path, 'w') as f:
            yaml.dump({
                'root': True,
                'rules': {'disable': ['E501']}
            }, f)

        cfg = RevealConfig.get(Path(self.temp_dir))
        dumped = cfg.dump()

        self.assertIsInstance(dumped, str)
        self.assertIn('rules', dumped)
        self.assertIn('E501', dumped)


if __name__ == '__main__':
    unittest.main()
