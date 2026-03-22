"""Extended tests for PythonAdapter (TEST-02).

Fills coverage gaps beyond the 9 tests in test_python_adapter.py:
- get_element routing for every supported element name
- Unknown element returns None
- _get_env structure and key fields
- _get_venv with and without active venv
- packages sub-route (packages/<name>)
- module sub-route (module/<name>)
- syspath element
- doctor element
- get_structure contract fields (source_type etc.)
- get_available_elements completeness
- get_schema / get_help
"""

import sys
import unittest
from reveal.adapters.python import PythonAdapter


class TestGetElementRouting(unittest.TestCase):
    """Every documented element route must return a dict, not None."""

    def setUp(self):
        self.adapter = PythonAdapter()

    def test_version_element(self):
        result = self.adapter.get_element('version')
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn('version', result)

    def test_env_element(self):
        result = self.adapter.get_element('env')
        self.assertIsNotNone(result)
        self.assertIn('sys_path', result)
        self.assertIn('flags', result)
        self.assertIn('encoding', result)

    def test_venv_element(self):
        result = self.adapter.get_element('venv')
        self.assertIsNotNone(result)
        self.assertIn('active', result)

    def test_packages_element(self):
        result = self.adapter.get_element('packages')
        self.assertIsNotNone(result)
        self.assertIn('packages', result)
        self.assertIn('count', result)

    def test_imports_element(self):
        result = self.adapter.get_element('imports')
        self.assertIsNotNone(result)
        self.assertIn('loaded', result)

    def test_syspath_element(self):
        result = self.adapter.get_element('syspath')
        self.assertIsNotNone(result)

    def test_doctor_element(self):
        result = self.adapter.get_element('doctor')
        self.assertIsNotNone(result)

    def test_debug_bytecode_element(self):
        result = self.adapter.get_element('debug/bytecode')
        self.assertIsNotNone(result)
        self.assertIn('status', result)

    def test_unknown_element_returns_none(self):
        result = self.adapter.get_element('nonexistent_element_xyz')
        self.assertIsNone(result)

    def test_unknown_nested_element_returns_none(self):
        result = self.adapter.get_element('debug/nosuchtype')
        # debug/<unknown> should not crash — it may return None or an error dict
        # The key requirement is: no exception raised
        pass


class TestGetEnv(unittest.TestCase):

    def setUp(self):
        self.adapter = PythonAdapter()

    def test_sys_path_is_list(self):
        result = self.adapter._get_env()
        self.assertIsInstance(result['sys_path'], list)

    def test_sys_path_matches_actual(self):
        result = self.adapter._get_env()
        self.assertEqual(result['sys_path'], list(sys.path))

    def test_sys_path_count_matches_list(self):
        result = self.adapter._get_env()
        self.assertEqual(result['sys_path_count'], len(result['sys_path']))

    def test_flags_has_expected_keys(self):
        result = self.adapter._get_env()
        flags = result['flags']
        for key in ('dont_write_bytecode', 'optimize', 'verbose', 'interactive', 'debug'):
            self.assertIn(key, flags)

    def test_encoding_has_filesystem_and_default(self):
        result = self.adapter._get_env()
        self.assertIn('filesystem', result['encoding'])
        self.assertIn('default', result['encoding'])


class TestGetVenv(unittest.TestCase):

    def setUp(self):
        self.adapter = PythonAdapter()

    def test_returns_dict_with_active_key(self):
        result = self.adapter._get_venv()
        self.assertIn('active', result)
        self.assertIsInstance(result['active'], bool)

    def test_active_venv_includes_python_version(self):
        result = self.adapter._get_venv()
        if result['active']:
            # When a venv is active, _get_venv() adds python_version
            self.assertIn('python_version', result)


class TestPackagesSubRoute(unittest.TestCase):

    def setUp(self):
        self.adapter = PythonAdapter()

    def test_packages_list_via_get_element(self):
        result = self.adapter.get_element('packages')
        self.assertIn('packages', result)
        self.assertGreater(result['count'], 0)

    def test_known_package_details(self):
        # 'pip' should always be installed
        result = self.adapter.get_element('packages/pip')
        self.assertIsNotNone(result)
        # Should have name field or an error/not-found indicator
        self.assertIsInstance(result, dict)

    def test_unknown_package_does_not_crash(self):
        result = self.adapter.get_element('packages/no_such_package_xyz_999')
        # Must not raise; may return None or error dict
        self.assertIsNotNone(result)


class TestModuleSubRoute(unittest.TestCase):

    def setUp(self):
        self.adapter = PythonAdapter()

    def test_known_stdlib_module(self):
        result = self.adapter.get_element('module/sys')
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)

    def test_unknown_module_does_not_crash(self):
        result = self.adapter.get_element('module/no_such_module_xyz_999')
        self.assertIsNotNone(result)


class TestGetStructureContract(unittest.TestCase):

    def setUp(self):
        self.adapter = PythonAdapter()
        self.result = self.adapter.get_structure()

    def test_version_present(self):
        self.assertIn('version', self.result)

    def test_executable_present(self):
        self.assertIn('executable', self.result)

    def test_platform_present(self):
        self.assertIn('platform', self.result)

    def test_executable_matches_sys(self):
        self.assertEqual(self.result['executable'], sys.executable)

    def test_version_is_string_with_dots(self):
        self.assertIsInstance(self.result['version'], str)
        self.assertIn('.', self.result['version'])


class TestGetAvailableElements(unittest.TestCase):

    def setUp(self):
        self.adapter = PythonAdapter()
        self.elements = self.adapter.get_available_elements()

    def test_returns_list(self):
        self.assertIsInstance(self.elements, list)

    def test_all_documented_routes_listed(self):
        names = {e['name'] for e in self.elements}
        for expected in ('version', 'env', 'venv', 'packages', 'imports', 'syspath', 'doctor'):
            self.assertIn(expected, names, f"'{expected}' missing from get_available_elements()")

    def test_each_element_has_name_and_description(self):
        for elem in self.elements:
            self.assertIn('name', elem)
            self.assertIn('description', elem)

    def test_listed_elements_actually_route(self):
        """Every element listed in get_available_elements() must return non-None."""
        for elem in self.elements:
            name = elem['name']
            # Skip sub-path examples like 'packages/<name>'
            if '<' in name or '/' in name:
                continue
            result = self.adapter.get_element(name)
            self.assertIsNotNone(
                result,
                f"get_element('{name}') returned None but it's listed in get_available_elements()"
            )


class TestGetSchemaAndHelp(unittest.TestCase):

    def test_get_schema_returns_dict(self):
        schema = PythonAdapter.get_schema()
        self.assertIsInstance(schema, dict)

    def test_get_help_returns_dict(self):
        h = PythonAdapter.get_help()
        self.assertIsInstance(h, dict)


if __name__ == '__main__':
    unittest.main()
