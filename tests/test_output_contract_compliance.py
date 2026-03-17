"""Output contract compliance tests for all locally-testable adapters.

Verifies that get_structure() returns dicts satisfying Output Contract v1.0:
  - contract_version: present and non-empty
  - type: present, non-empty, snake_case
  - source: present and non-empty
  - source_type: one of the allowed values

Also verifies schema-to-output alignment: the actual 'type' field must appear
in the adapter's get_schema()['output_types'] list.

Network/external adapters (mysql, ssl, domain, autossl, cpanel) are skipped
with a documented reason. They need real external services to produce output.
"""

import re
import sqlite3
import tempfile
import os
import unittest

from reveal.adapters.base import get_adapter_class


# Required contract fields for v1.0
_REQUIRED_FIELDS = ['contract_version', 'type', 'source', 'source_type']
_VALID_SOURCE_TYPES = {'file', 'directory', 'database', 'runtime', 'network'}
_TYPE_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


def _check_contract(test_case, adapter_name, result):
    """Assert that result satisfies Output Contract v1.0."""
    test_case.assertIsInstance(
        result, dict,
        f"{adapter_name}: get_structure() must return a dict, got {type(result).__name__}"
    )
    for field in _REQUIRED_FIELDS:
        test_case.assertIn(
            field, result,
            f"{adapter_name}: missing required field '{field}' in get_structure() output"
        )
        test_case.assertTrue(
            result[field],
            f"{adapter_name}: required field '{field}' is empty or falsy"
        )
    test_case.assertRegex(
        result['type'], _TYPE_PATTERN,
        f"{adapter_name}: 'type' field must be snake_case, got {result['type']!r}"
    )
    test_case.assertIn(
        result['source_type'], _VALID_SOURCE_TYPES,
        f"{adapter_name}: 'source_type' must be one of {sorted(_VALID_SOURCE_TYPES)}, "
        f"got {result['source_type']!r}"
    )


def _check_schema_alignment(test_case, adapter_name, result, schema):
    """Assert that result['type'] appears in the adapter's declared output_types."""
    if not schema:
        return
    declared = {ot['type'] for ot in schema.get('output_types', [])}
    if not declared:
        return
    actual_type = result.get('type', '')
    test_case.assertIn(
        actual_type, declared,
        f"{adapter_name}: output type {actual_type!r} not in schema output_types "
        f"{sorted(declared)[:8]} (truncated). "
        f"Add it to _SCHEMA_OUTPUT_TYPES or fix the adapter's 'type' field."
    )


class TestOutputContractEnv(unittest.TestCase):
    """env:// adapter — no external resources needed."""

    def test_get_structure_contract(self):
        from reveal.adapters import env
        result = env.EnvAdapter().get_structure()
        _check_contract(self, 'env', result)

    def test_schema_alignment(self):
        from reveal.adapters import env
        result = env.EnvAdapter().get_structure()
        _check_schema_alignment(self, 'env', result, env.EnvAdapter.get_schema())


class TestOutputContractPython(unittest.TestCase):
    """python:// adapter — no external resources needed."""

    def test_get_structure_contract(self):
        from reveal.adapters import python as pya
        result = pya.PythonAdapter().get_structure()
        _check_contract(self, 'python', result)

    def test_schema_alignment(self):
        from reveal.adapters import python as pya
        result = pya.PythonAdapter().get_structure()
        _check_schema_alignment(self, 'python', result, pya.PythonAdapter.get_schema())


class TestOutputContractAst(unittest.TestCase):
    """ast:// adapter — needs a temp Python file."""

    def setUp(self):
        self._td = tempfile.mkdtemp()
        self._py = os.path.join(self._td, 'foo.py')
        with open(self._py, 'w') as f:
            f.write('def foo():\n    pass\n\ndef bar():\n    return foo()\n')

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def test_get_structure_contract(self):
        from reveal.adapters import ast as astmod
        result = astmod.AstAdapter(self._py).get_structure()
        _check_contract(self, 'ast', result)

    def test_schema_alignment(self):
        from reveal.adapters import ast as astmod
        result = astmod.AstAdapter(self._py).get_structure()
        _check_schema_alignment(self, 'ast', result, astmod.AstAdapter.get_schema())


class TestOutputContractJson(unittest.TestCase):
    """json:// adapter — needs a temp JSON file."""

    def setUp(self):
        self._td = tempfile.mkdtemp()
        self._jf = os.path.join(self._td, 'data.json')
        with open(self._jf, 'w') as f:
            f.write('{"key": "value", "count": 42}')

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def test_get_structure_contract(self):
        from reveal.adapters import json as jadapter
        result = jadapter.JsonAdapter(self._jf).get_structure()
        _check_contract(self, 'json', result)

    def test_schema_alignment(self):
        from reveal.adapters import json as jadapter
        result = jadapter.JsonAdapter(self._jf).get_structure()
        _check_schema_alignment(self, 'json', result, jadapter.JsonAdapter.get_schema())


class TestOutputContractStats(unittest.TestCase):
    """stats:// adapter — needs a temp directory with Python files."""

    def setUp(self):
        self._td = tempfile.mkdtemp()
        with open(os.path.join(self._td, 'foo.py'), 'w') as f:
            f.write('def foo(): pass\ndef bar(): return 1\n')

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def test_get_structure_contract(self):
        from reveal.adapters import stats
        result = stats.StatsAdapter(self._td).get_structure()
        _check_contract(self, 'stats', result)

    def test_schema_alignment(self):
        from reveal.adapters import stats
        result = stats.StatsAdapter(self._td).get_structure()
        _check_schema_alignment(self, 'stats', result, stats.StatsAdapter.get_schema())


class TestOutputContractSqlite(unittest.TestCase):
    """sqlite:// adapter — needs a temp SQLite database."""

    def setUp(self):
        self._td = tempfile.mkdtemp()
        self._db = os.path.join(self._td, 'test.db')
        conn = sqlite3.connect(self._db)
        conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
        conn.commit()
        conn.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def test_get_structure_contract(self):
        from reveal.adapters import sqlite
        result = sqlite.SQLiteAdapter(f'sqlite://{self._db}').get_structure()
        _check_contract(self, 'sqlite', result)

    def test_schema_alignment(self):
        from reveal.adapters import sqlite
        result = sqlite.SQLiteAdapter(f'sqlite://{self._db}').get_structure()
        _check_schema_alignment(self, 'sqlite', result, sqlite.SQLiteAdapter.get_schema())


class TestOutputContractImports(unittest.TestCase):
    """imports:// adapter — uses current working directory."""

    def test_get_structure_contract(self):
        from reveal.adapters import imports as impadapter
        result = impadapter.ImportsAdapter().get_structure()
        _check_contract(self, 'imports', result)

    def test_schema_alignment(self):
        from reveal.adapters import imports as impadapter
        result = impadapter.ImportsAdapter().get_structure()
        _check_schema_alignment(self, 'imports', result, impadapter.ImportsAdapter.get_schema())


class TestOutputContractCalls(unittest.TestCase):
    """calls:// adapter — needs a temp directory with Python files."""

    def setUp(self):
        self._td = tempfile.mkdtemp()
        with open(os.path.join(self._td, 'app.py'), 'w') as f:
            f.write('def main():\n    helper()\n\ndef helper():\n    pass\n')

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def test_get_structure_contract(self):
        from reveal.adapters.calls.adapter import CallsAdapter
        result = CallsAdapter(self._td).get_structure()
        _check_contract(self, 'calls', result)

    def test_schema_alignment(self):
        from reveal.adapters.calls.adapter import CallsAdapter
        result = CallsAdapter(self._td).get_structure()
        _check_schema_alignment(self, 'calls', result, CallsAdapter.get_schema())


class TestOutputContractDiff(unittest.TestCase):
    """diff:// adapter — uses git:// URIs against the current repo."""

    def test_get_structure_contract(self):
        from reveal.adapters.diff.adapter import DiffAdapter
        result = DiffAdapter('git://HEAD/.', 'git://HEAD/.').get_structure()
        _check_contract(self, 'diff', result)

    def test_schema_alignment(self):
        from reveal.adapters.diff.adapter import DiffAdapter
        result = DiffAdapter('git://HEAD/.', 'git://HEAD/.').get_structure()
        _check_schema_alignment(self, 'diff', result, DiffAdapter.get_schema())


class TestOutputContractGit(unittest.TestCase):
    """git:// adapter — uses the current git repository."""

    def test_get_structure_contract(self):
        from reveal.adapters.git.adapter import GitAdapter
        result = GitAdapter('.').get_structure()
        _check_contract(self, 'git', result)

    def test_schema_alignment(self):
        from reveal.adapters.git.adapter import GitAdapter
        result = GitAdapter('.').get_structure()
        _check_schema_alignment(self, 'git', result, GitAdapter.get_schema())


class TestOutputContractMarkdown(unittest.TestCase):
    """markdown:// adapter — needs a temp directory with .md files."""

    def setUp(self):
        self._td = tempfile.mkdtemp()
        with open(os.path.join(self._td, 'README.md'), 'w') as f:
            f.write('# Test\n\nHello world.\n')

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def test_get_structure_contract(self):
        from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
        result = MarkdownQueryAdapter(base_path=self._td, query=None).get_structure()
        _check_contract(self, 'markdown', result)

    def test_schema_alignment(self):
        from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
        result = MarkdownQueryAdapter(base_path=self._td, query=None).get_structure()
        _check_schema_alignment(self, 'markdown', result, MarkdownQueryAdapter.get_schema())


class TestOutputContractNginx(unittest.TestCase):
    """nginx:// adapter — overview mode searches system nginx dirs."""

    def test_get_structure_contract(self):
        from reveal.adapters.nginx.adapter import NginxUriAdapter
        result = NginxUriAdapter('nginx://').get_structure()
        _check_contract(self, 'nginx', result)

    def test_schema_alignment(self):
        from reveal.adapters.nginx.adapter import NginxUriAdapter
        result = NginxUriAdapter('nginx://').get_structure()
        _check_schema_alignment(self, 'nginx', result, NginxUriAdapter.get_schema())


class TestOutputContractReveal(unittest.TestCase):
    """reveal:// adapter — no external resources needed."""

    def test_get_structure_contract(self):
        cls = get_adapter_class('reveal')
        result = cls().get_structure()
        _check_contract(self, 'reveal', result)

    def test_schema_alignment(self):
        cls = get_adapter_class('reveal')
        result = cls().get_structure()
        _check_schema_alignment(self, 'reveal', result, cls.get_schema())


class TestOutputContractClaude(unittest.TestCase):
    """claude:// adapter — sessions listing requires ~/.claude/projects."""

    def test_get_structure_contract(self):
        cls = get_adapter_class('claude')
        result = cls('sessions').get_structure()
        _check_contract(self, 'claude', result)

    def test_schema_alignment(self):
        cls = get_adapter_class('claude')
        result = cls('sessions').get_structure()
        _check_schema_alignment(self, 'claude', result, cls.get_schema())


class TestOutputContractXlsx(unittest.TestCase):
    """xlsx:// adapter — needs a temp Excel file."""

    def setUp(self):
        try:
            import openpyxl
            self._has_openpyxl = True
        except ImportError:
            self._has_openpyxl = False
        self._td = tempfile.mkdtemp()
        self._xlsx = os.path.join(self._td, 'data.xlsx')

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def _create_xlsx(self):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Sheet1'
        ws.append(['Name', 'Value'])
        ws.append(['foo', 42])
        wb.save(self._xlsx)

    def test_get_structure_contract(self):
        if not self._has_openpyxl:
            self.skipTest('openpyxl not installed')
        self._create_xlsx()
        from reveal.adapters.xlsx import XlsxAdapter
        result = XlsxAdapter(self._xlsx).get_structure()
        _check_contract(self, 'xlsx', result)

    def test_schema_alignment(self):
        if not self._has_openpyxl:
            self.skipTest('openpyxl not installed')
        self._create_xlsx()
        from reveal.adapters.xlsx import XlsxAdapter
        result = XlsxAdapter(self._xlsx).get_structure()
        _check_schema_alignment(self, 'xlsx', result, XlsxAdapter.get_schema())


class TestNetworkAdaptersSkipped(unittest.TestCase):
    """Document network/external adapters that require real services.

    These adapters cannot be conformance-tested without external infrastructure.
    They are listed here to make the omission explicit and intentional.
    """

    def test_mysql_requires_server(self):
        """mysql:// requires a live MySQL/MariaDB server."""
        self.skipTest(
            'mysql:// requires a live MySQL server. '
            'Test manually with: reveal mysql://localhost:3306/dbname'
        )

    def test_ssl_requires_network(self):
        """ssl:// requires a real TLS endpoint to connect to."""
        self.skipTest(
            'ssl:// requires a live TLS endpoint. '
            'Test manually with: reveal ssl://example.com:443'
        )

    def test_domain_requires_dns(self):
        """domain:// requires real DNS resolution."""
        self.skipTest(
            'domain:// requires live DNS resolution. '
            'Test manually with: reveal domain://example.com'
        )

    def test_autossl_requires_logs(self):
        """autossl:// requires real renewal log files."""
        self.skipTest(
            'autossl:// requires renewal log files at /var/log/letsencrypt/. '
            'Test manually on a server with certbot.'
        )

    def test_cpanel_requires_server(self):
        """cpanel:// requires a live cPanel server."""
        self.skipTest(
            'cpanel:// requires a live cPanel server. '
            'Test manually with: reveal cpanel://username'
        )


if __name__ == '__main__':
    unittest.main()
