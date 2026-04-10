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

    @classmethod
    def setUpClass(cls):
        from reveal.adapters import env
        cls.result = env.EnvAdapter().get_structure()
        cls.schema = env.EnvAdapter.get_schema()

    def test_get_structure_contract(self):
        _check_contract(self, 'env', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'env', self.result, self.schema)


class TestOutputContractPython(unittest.TestCase):
    """python:// adapter — no external resources needed."""

    @classmethod
    def setUpClass(cls):
        from reveal.adapters import python as pya
        cls.result = pya.PythonAdapter().get_structure()
        cls.schema = pya.PythonAdapter.get_schema()

    def test_get_structure_contract(self):
        _check_contract(self, 'python', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'python', self.result, self.schema)


class TestOutputContractAst(unittest.TestCase):
    """ast:// adapter — needs a temp Python file."""

    @classmethod
    def setUpClass(cls):
        import shutil
        from reveal.adapters import ast as astmod
        cls._td = tempfile.mkdtemp()
        py = os.path.join(cls._td, 'foo.py')
        with open(py, 'w') as f:
            f.write('def foo():\n    pass\n\ndef bar():\n    return foo()\n')
        cls.result = astmod.AstAdapter(py).get_structure()
        cls.schema = astmod.AstAdapter.get_schema()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_get_structure_contract(self):
        _check_contract(self, 'ast', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'ast', self.result, self.schema)


class TestOutputContractJson(unittest.TestCase):
    """json:// adapter — needs a temp JSON file."""

    @classmethod
    def setUpClass(cls):
        from reveal.adapters import json as jadapter
        cls._td = tempfile.mkdtemp()
        jf = os.path.join(cls._td, 'data.json')
        with open(jf, 'w') as f:
            f.write('{"key": "value", "count": 42}')
        cls.result = jadapter.JsonAdapter(jf).get_structure()
        cls.schema = jadapter.JsonAdapter.get_schema()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_get_structure_contract(self):
        _check_contract(self, 'json', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'json', self.result, self.schema)


class TestOutputContractStats(unittest.TestCase):
    """stats:// adapter — needs a temp directory with Python files."""

    @classmethod
    def setUpClass(cls):
        from reveal.adapters import stats
        cls._td = tempfile.mkdtemp()
        with open(os.path.join(cls._td, 'foo.py'), 'w') as f:
            f.write('def foo(): pass\ndef bar(): return 1\n')
        cls.result = stats.StatsAdapter(cls._td).get_structure()
        cls.schema = stats.StatsAdapter.get_schema()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_get_structure_contract(self):
        _check_contract(self, 'stats', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'stats', self.result, self.schema)


class TestOutputContractSqlite(unittest.TestCase):
    """sqlite:// adapter — needs a temp SQLite database."""

    @classmethod
    def setUpClass(cls):
        from reveal.adapters import sqlite
        cls._td = tempfile.mkdtemp()
        db = os.path.join(cls._td, 'test.db')
        conn = sqlite3.connect(db)
        conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
        conn.commit()
        conn.close()
        cls.result = sqlite.SQLiteAdapter(f'sqlite://{db}').get_structure()
        cls.schema = sqlite.SQLiteAdapter.get_schema()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_get_structure_contract(self):
        _check_contract(self, 'sqlite', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'sqlite', self.result, self.schema)


class TestOutputContractImports(unittest.TestCase):
    """imports:// adapter — uses a small fixture directory (not the full CWD)."""

    @classmethod
    def setUpClass(cls):
        import shutil
        from reveal.adapters import imports as impadapter
        cls._td = tempfile.mkdtemp()
        with open(os.path.join(cls._td, 'main.py'), 'w') as f:
            f.write('import os\nimport sys\n\ndef main():\n    pass\n')
        cls.result = impadapter.ImportsAdapter(cls._td).get_structure()
        cls.schema = impadapter.ImportsAdapter.get_schema()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_get_structure_contract(self):
        _check_contract(self, 'imports', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'imports', self.result, self.schema)


class TestOutputContractCalls(unittest.TestCase):
    """calls:// adapter — needs a temp directory with Python files."""

    @classmethod
    def setUpClass(cls):
        from reveal.adapters.calls.adapter import CallsAdapter
        cls._td = tempfile.mkdtemp()
        with open(os.path.join(cls._td, 'app.py'), 'w') as f:
            f.write('def main():\n    helper()\n\ndef helper():\n    pass\n')
        cls.result = CallsAdapter(cls._td).get_structure()
        cls.schema = CallsAdapter.get_schema()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_get_structure_contract(self):
        _check_contract(self, 'calls', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'calls', self.result, self.schema)


class TestOutputContractDiff(unittest.TestCase):
    """diff:// adapter — diffs a single small file against itself (HEAD vs HEAD)."""

    @classmethod
    def setUpClass(cls):
        from reveal.adapters.diff.adapter import DiffAdapter
        # Target a single small file to avoid traversing the full project tree.
        cls.result = DiffAdapter('git://HEAD/reveal/version.py', 'git://HEAD/reveal/version.py').get_structure()
        cls.schema = DiffAdapter.get_schema()

    def test_get_structure_contract(self):
        _check_contract(self, 'diff', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'diff', self.result, self.schema)


class TestOutputContractGit(unittest.TestCase):
    """git:// adapter — uses the current git repository."""

    @classmethod
    def setUpClass(cls):
        from reveal.adapters.git.adapter import GitAdapter
        cls.result = GitAdapter('.').get_structure()
        cls.schema = GitAdapter.get_schema()

    def test_get_structure_contract(self):
        _check_contract(self, 'git', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'git', self.result, self.schema)


class TestOutputContractMarkdown(unittest.TestCase):
    """markdown:// adapter — needs a temp directory with .md files."""

    @classmethod
    def setUpClass(cls):
        from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
        cls._td = tempfile.mkdtemp()
        with open(os.path.join(cls._td, 'README.md'), 'w') as f:
            f.write('# Test\n\nHello world.\n')
        cls.result = MarkdownQueryAdapter(base_path=cls._td, query=None).get_structure()
        cls.schema = MarkdownQueryAdapter.get_schema()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._td, ignore_errors=True)

    def test_get_structure_contract(self):
        _check_contract(self, 'markdown', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'markdown', self.result, self.schema)


class TestOutputContractNginx(unittest.TestCase):
    """nginx:// adapter — overview mode searches system nginx dirs."""

    @classmethod
    def setUpClass(cls):
        from reveal.adapters.nginx.adapter import NginxUriAdapter
        cls.result = NginxUriAdapter('nginx://').get_structure()
        cls.schema = NginxUriAdapter.get_schema()

    def test_get_structure_contract(self):
        _check_contract(self, 'nginx', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'nginx', self.result, self.schema)


class TestOutputContractReveal(unittest.TestCase):
    """reveal:// adapter — no external resources needed."""

    @classmethod
    def setUpClass(cls):
        adapter_cls = get_adapter_class('reveal')
        cls.result = adapter_cls().get_structure()
        cls.schema = adapter_cls.get_schema()

    def test_get_structure_contract(self):
        _check_contract(self, 'reveal', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'reveal', self.result, self.schema)


class TestOutputContractClaude(unittest.TestCase):
    """claude:// adapter — sessions listing requires ~/.claude/projects."""

    @classmethod
    def setUpClass(cls):
        adapter_cls = get_adapter_class('claude')
        cls.result = adapter_cls('sessions').get_structure()
        cls.schema = adapter_cls.get_schema()

    def test_get_structure_contract(self):
        _check_contract(self, 'claude', self.result)

    def test_schema_alignment(self):
        _check_schema_alignment(self, 'claude', self.result, self.schema)


class TestOutputContractXlsx(unittest.TestCase):
    """xlsx:// adapter — needs a temp Excel file."""

    @classmethod
    def setUpClass(cls):
        try:
            import openpyxl
            cls._has_openpyxl = True
        except ImportError:
            cls._has_openpyxl = False
            cls.result = None
            cls.schema = None
            return
        from reveal.adapters.xlsx import XlsxAdapter
        cls._td = tempfile.mkdtemp()
        xlsx = os.path.join(cls._td, 'data.xlsx')
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Sheet1'
        ws.append(['Name', 'Value'])
        ws.append(['foo', 42])
        wb.save(xlsx)
        cls.result = XlsxAdapter(xlsx).get_structure()
        cls.schema = XlsxAdapter.get_schema()

    @classmethod
    def tearDownClass(cls):
        if cls._has_openpyxl:
            import shutil
            shutil.rmtree(cls._td, ignore_errors=True)

    def test_get_structure_contract(self):
        if not self._has_openpyxl:
            self.skipTest('openpyxl not installed')
        _check_contract(self, 'xlsx', self.result)

    def test_schema_alignment(self):
        if not self._has_openpyxl:
            self.skipTest('openpyxl not installed')
        _check_schema_alignment(self, 'xlsx', self.result, self.schema)


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
