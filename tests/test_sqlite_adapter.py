"""Comprehensive tests for SQLite adapter.

Tests cover:
- Adapter initialization and URI parsing
- Database overview extraction
- Table structure inspection
- Foreign key relationships
- Index detection
- In-memory and file-based databases
- Error handling
"""

import unittest
import sqlite3
import tempfile
import os
from pathlib import Path
import sys

# Add parent directory to path to import reveal
sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.adapters.sqlite import SQLiteAdapter


class TestSQLiteAdapterInit(unittest.TestCase):
    """Test SQLite adapter initialization and URI parsing."""

    def test_init_with_empty_uri(self):
        """Should raise ValueError for empty URI."""
        with self.assertRaises(ValueError):
            SQLiteAdapter("")

    def test_init_with_minimal_uri(self):
        """Should raise ValueError for minimal URI without path."""
        with self.assertRaises(ValueError):
            SQLiteAdapter("sqlite://")

    def test_init_with_absolute_path(self):
        """Should parse absolute path correctly."""
        adapter = SQLiteAdapter("sqlite:///tmp/test.db")
        self.assertEqual(adapter.db_path, "/tmp/test.db")
        self.assertIsNone(adapter.table)

    def test_init_with_relative_path(self):
        """Should parse relative path correctly."""
        adapter = SQLiteAdapter("sqlite://./test.db")
        self.assertEqual(adapter.db_path, "./test.db")
        self.assertIsNone(adapter.table)

    def test_init_with_table(self):
        """Should parse path with table name."""
        adapter = SQLiteAdapter("sqlite:///tmp/test.db/users")
        self.assertEqual(adapter.db_path, "/tmp/test.db")
        self.assertEqual(adapter.table, "users")

    def test_init_with_nested_path(self):
        """Should parse nested path correctly."""
        adapter = SQLiteAdapter("sqlite:///var/data/app.db/accounts")
        self.assertEqual(adapter.db_path, "/var/data/app.db")
        self.assertEqual(adapter.table, "accounts")


class TestSQLiteAdapterStructure(unittest.TestCase):
    """Test SQLite database structure extraction."""

    def setUp(self):
        """Create temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Create test schema
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create users table
        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create posts table with foreign key
        cursor.execute("""
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                published BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Create index on posts
        cursor.execute("CREATE INDEX idx_posts_user_id ON posts(user_id)")
        cursor.execute("CREATE UNIQUE INDEX idx_posts_title ON posts(title)")

        # Create a view
        cursor.execute("""
            CREATE VIEW user_posts AS
            SELECT u.username, p.title, p.content
            FROM users u
            JOIN posts p ON u.id = p.user_id
        """)

        # Insert test data
        cursor.execute("INSERT INTO users (username, email) VALUES ('alice', 'alice@example.com')")
        cursor.execute("INSERT INTO users (username, email) VALUES ('bob', 'bob@example.com')")
        cursor.execute("INSERT INTO posts (user_id, title, content, published) VALUES (1, 'Hello World', 'First post', 1)")
        cursor.execute("INSERT INTO posts (user_id, title, content, published) VALUES (1, 'Second Post', 'Another post', 0)")
        cursor.execute("INSERT INTO posts (user_id, title, content, published) VALUES (2, 'Bob Post', 'Bob writes', 1)")

        conn.commit()
        conn.close()

    def tearDown(self):
        """Remove temporary database."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_get_structure_basic(self):
        """Should return database overview with basic info."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        structure = adapter.get_structure()

        self.assertEqual(structure['type'], 'sqlite_database')
        self.assertEqual(structure['path'], self.db_path)
        self.assertIn('size', structure)
        self.assertIn('sqlite_version', structure)

    def test_get_structure_configuration(self):
        """Should return SQLite configuration details."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        structure = adapter.get_structure()

        self.assertIn('configuration', structure)
        config = structure['configuration']
        self.assertIn('page_size', config)
        self.assertIn('journal_mode', config)
        self.assertIn('encoding', config)

    def test_get_structure_statistics(self):
        """Should return accurate database statistics."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        structure = adapter.get_structure()

        self.assertIn('statistics', structure)
        stats = structure['statistics']
        self.assertEqual(stats['tables'], 2)  # users, posts
        self.assertEqual(stats['views'], 1)   # user_posts
        self.assertEqual(stats['total_rows'], 5)  # 2 users + 3 posts
        self.assertEqual(stats['foreign_keys'], 1)  # posts -> users

    def test_get_structure_tables_list(self):
        """Should return list of tables with details."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        structure = adapter.get_structure()

        self.assertIn('tables', structure)
        tables = structure['tables']
        self.assertEqual(len(tables), 3)  # users, posts, user_posts

        # Check users table
        users_table = next(t for t in tables if t['name'] == 'users')
        self.assertEqual(users_table['type'], 'table')
        self.assertEqual(users_table['rows'], 2)
        self.assertEqual(users_table['columns'], 4)  # id, username, email, created_at
        # Note: UNIQUE constraint creates sqlite_autoindex_* which we filter out
        self.assertEqual(users_table['indexes'], 0)

        # Check posts table
        posts_table = next(t for t in tables if t['name'] == 'posts')
        self.assertEqual(posts_table['type'], 'table')
        self.assertEqual(posts_table['rows'], 3)
        self.assertEqual(posts_table['columns'], 5)
        self.assertEqual(posts_table['indexes'], 2)  # idx_posts_user_id, idx_posts_title

        # Check view
        view = next(t for t in tables if t['name'] == 'user_posts')
        self.assertEqual(view['type'], 'view')
        self.assertEqual(view['columns'], 3)

    def test_get_structure_next_steps(self):
        """Should provide helpful next steps."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        structure = adapter.get_structure()

        self.assertIn('next_steps', structure)
        self.assertIsInstance(structure['next_steps'], list)
        self.assertTrue(len(structure['next_steps']) > 0)


class TestSQLiteAdapterElement(unittest.TestCase):
    """Test SQLite table inspection."""

    def setUp(self):
        """Create temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Create test schema
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                age INTEGER,
                bio TEXT DEFAULT 'No bio',
                is_active BOOLEAN DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
            )
        """)

        cursor.execute("CREATE INDEX idx_posts_user_id ON posts(user_id)")
        cursor.execute("CREATE UNIQUE INDEX idx_posts_title ON posts(title)")

        cursor.execute("INSERT INTO users (username, email, age) VALUES ('alice', 'alice@example.com', 30)")
        cursor.execute("INSERT INTO posts (user_id, title) VALUES (1, 'Hello World')")

        conn.commit()
        conn.close()

    def tearDown(self):
        """Remove temporary database."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_get_element_basic(self):
        """Should return table structure."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        element = adapter.get_element('users')

        self.assertIsNotNone(element)
        self.assertEqual(element['type'], 'sqlite_table')
        self.assertEqual(element['table'], 'users')
        self.assertEqual(element['database'], self.db_path)

    def test_get_element_columns(self):
        """Should return detailed column information."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        element = adapter.get_element('users')

        self.assertIn('columns', element)
        columns = element['columns']
        self.assertEqual(len(columns), 6)

        # Check id column
        id_col = next(c for c in columns if c['name'] == 'id')
        self.assertEqual(id_col['type'], 'INTEGER')
        self.assertFalse(id_col['nullable'])
        self.assertTrue(id_col['primary_key'])

        # Check username column
        username_col = next(c for c in columns if c['name'] == 'username')
        self.assertEqual(username_col['type'], 'TEXT')
        self.assertFalse(username_col['nullable'])
        self.assertFalse(username_col['primary_key'])

        # Check age column (nullable)
        age_col = next(c for c in columns if c['name'] == 'age')
        self.assertEqual(age_col['type'], 'INTEGER')
        self.assertTrue(age_col['nullable'])

        # Check bio column (with default)
        bio_col = next(c for c in columns if c['name'] == 'bio')
        self.assertEqual(bio_col['default'], "'No bio'")

    def test_get_element_indexes(self):
        """Should return index information."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        element = adapter.get_element('posts')

        self.assertIn('indexes', element)
        indexes = element['indexes']
        self.assertEqual(len(indexes), 2)

        # Check regular index
        user_idx = next(idx for idx in indexes if idx['name'] == 'idx_posts_user_id')
        self.assertEqual(user_idx['columns'], ['user_id'])
        self.assertFalse(user_idx['unique'])

        # Check unique index
        title_idx = next(idx for idx in indexes if idx['name'] == 'idx_posts_title')
        self.assertEqual(title_idx['columns'], ['title'])
        self.assertTrue(title_idx['unique'])

    def test_get_element_foreign_keys(self):
        """Should return foreign key relationships."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        element = adapter.get_element('posts')

        self.assertIn('foreign_keys', element)
        fks = element['foreign_keys']
        self.assertEqual(len(fks), 1)

        fk = fks[0]
        self.assertEqual(fk['column'], 'user_id')
        self.assertEqual(fk['references_table'], 'users')
        self.assertEqual(fk['references_column'], 'id')
        self.assertEqual(fk['on_delete'], 'CASCADE')
        self.assertEqual(fk['on_update'], 'CASCADE')

    def test_get_element_row_count(self):
        """Should return accurate row count."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        element = adapter.get_element('users')

        self.assertIn('row_count', element)
        self.assertEqual(element['row_count'], 1)

    def test_get_element_create_statement(self):
        """Should return CREATE TABLE statement."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        element = adapter.get_element('users')

        self.assertIn('create_statement', element)
        self.assertIsNotNone(element['create_statement'])
        self.assertIn('CREATE TABLE', element['create_statement'])
        self.assertIn('users', element['create_statement'])

    def test_get_element_not_found(self):
        """Should return None for non-existent table."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        element = adapter.get_element('nonexistent')

        self.assertIsNone(element)

    def test_get_element_via_uri(self):
        """Should support table access via URI."""
        adapter = SQLiteAdapter(f"sqlite://{self.db_path}/users")
        structure = adapter.get_structure()

        # When table is in URI, get_structure delegates to get_element
        self.assertEqual(structure['type'], 'sqlite_table')
        self.assertEqual(structure['table'], 'users')


class TestSQLiteAdapterErrors(unittest.TestCase):
    """Test error handling."""

    def test_nonexistent_database(self):
        """Should raise FileNotFoundError for missing database."""
        adapter = SQLiteAdapter("sqlite:///nonexistent/path/to/db.db")

        with self.assertRaises(FileNotFoundError):
            adapter.get_structure()

    def test_nonexistent_table_via_uri(self):
        """Should raise ValueError for non-existent table in URI."""
        # Create empty database
        temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        temp_db.close()
        db_path = temp_db.name

        try:
            conn = sqlite3.connect(db_path)
            conn.close()

            adapter = SQLiteAdapter(f"sqlite://{db_path}/nonexistent")

            with self.assertRaises(ValueError):
                adapter.get_structure()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestSQLiteAdapterHelp(unittest.TestCase):
    """Test help documentation."""

    def test_get_help(self):
        """Should return help documentation."""
        help_info = SQLiteAdapter.get_help()

        self.assertIsNotNone(help_info)
        self.assertIn('name', help_info)
        self.assertEqual(help_info['name'], 'sqlite')
        self.assertIn('description', help_info)
        self.assertIn('syntax', help_info)
        self.assertIn('examples', help_info)
        self.assertTrue(len(help_info['examples']) > 0)


class TestSQLiteAdapterSchema(unittest.TestCase):
    """Test schema generation for AI agent integration."""

    def test_get_schema(self):
        """Should return machine-readable schema."""
        schema = SQLiteAdapter.get_schema()

        self.assertIsNotNone(schema)
        self.assertEqual(schema['adapter'], 'sqlite')
        self.assertIn('description', schema)
        self.assertIn('uri_syntax', schema)
        self.assertEqual(schema['uri_syntax'], 'sqlite:///path/to/db.db[/table]')

    def test_schema_query_params(self):
        """Schema should document query parameters."""
        schema = SQLiteAdapter.get_schema()

        self.assertIn('query_params', schema)
        self.assertIsInstance(schema['query_params'], dict)

    def test_schema_cli_flags(self):
        """Schema should document CLI flags."""
        schema = SQLiteAdapter.get_schema()

        self.assertIn('cli_flags', schema)
        self.assertIn('--check', schema['cli_flags'])

    def test_schema_output_types(self):
        """Schema should define output types."""
        schema = SQLiteAdapter.get_schema()

        self.assertIn('output_types', schema)
        self.assertTrue(len(schema['output_types']) >= 2)

        # Should have sqlite_database output type
        output_types = [ot['type'] for ot in schema['output_types']]
        self.assertIn('sqlite_database', output_types)
        self.assertIn('sqlite_table', output_types)

    def test_schema_examples(self):
        """Schema should include usage examples."""
        schema = SQLiteAdapter.get_schema()

        self.assertIn('example_queries', schema)
        self.assertTrue(len(schema['example_queries']) >= 3)

        # Examples should have required fields
        for example in schema['example_queries']:
            self.assertIn('uri', example)
            self.assertIn('description', example)


class TestSQLiteAdapterQuery(unittest.TestCase):
    """Test query execution methods."""

    def setUp(self):
        """Create temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Create test data
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                value INTEGER
            )
        """)

        cursor.execute("INSERT INTO test_table (name, value) VALUES ('Alice', 100)")
        cursor.execute("INSERT INTO test_table (name, value) VALUES ('Bob', 200)")
        cursor.execute("INSERT INTO test_table (name, value) VALUES ('Charlie', 300)")

        conn.commit()
        conn.close()

        self.adapter = SQLiteAdapter(f"sqlite://{self.db_path}")

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_execute_query_multiple_results(self):
        """_execute_query should return list of dicts."""
        results = self.adapter._execute_query("SELECT * FROM test_table ORDER BY id")

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]['name'], 'Alice')
        self.assertEqual(results[1]['name'], 'Bob')
        self.assertEqual(results[2]['name'], 'Charlie')

    def test_execute_query_empty_result(self):
        """_execute_query should return empty list for no results."""
        results = self.adapter._execute_query("SELECT * FROM test_table WHERE id = 999")

        self.assertEqual(results, [])

    def test_execute_single_one_result(self):
        """_execute_single should return single dict."""
        result = self.adapter._execute_single("SELECT name, value FROM test_table WHERE id = 2")

        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Bob')
        self.assertEqual(result['value'], 200)

    def test_execute_single_no_result(self):
        """_execute_single should return None for no results."""
        result = self.adapter._execute_single("SELECT * FROM test_table WHERE id = 999")

        self.assertIsNone(result)

    def test_execute_query_column_types(self):
        """Query results should handle different column types."""
        results = self.adapter._execute_query("SELECT id, name, value FROM test_table WHERE id = 1")

        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0]['id'], int)
        self.assertIsInstance(results[0]['name'], str)
        self.assertIsInstance(results[0]['value'], int)


class TestSQLiteRenderer(unittest.TestCase):
    """Test renderer output formatting."""

    def setUp(self):
        """Set up test database."""
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT
            )
        """)

        cursor.execute("CREATE INDEX idx_username ON users(username)")
        cursor.execute("INSERT INTO users (username, email) VALUES ('alice', 'alice@example.com')")

        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_renderer_database_overview(self):
        """Renderer should format database overview correctly."""
        from reveal.adapters.sqlite.renderer import SqliteRenderer
        from io import StringIO

        adapter = SQLiteAdapter(f"sqlite://{self.db_path}")
        result = adapter.get_structure()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        SqliteRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain key sections
        self.assertIn('SQLite Database:', output)
        self.assertIn('Version:', output)
        self.assertIn('Configuration:', output)
        self.assertIn('Statistics:', output)
        self.assertIn('Tables:', output)
        self.assertIn('users', output)

    def test_renderer_table_details(self):
        """Renderer should format table details correctly."""
        from reveal.adapters.sqlite.renderer import SqliteRenderer
        from io import StringIO

        adapter = SQLiteAdapter(f"sqlite://{self.db_path}/users")
        result = adapter.get_element('users')

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        SqliteRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain table details
        self.assertIn('Table: users', output)
        self.assertIn('Columns', output)
        self.assertIn('id', output)
        self.assertIn('username', output)
        self.assertIn('Indexes', output)
        self.assertIn('idx_username', output)

    def test_renderer_error_handling(self):
        """Renderer should handle errors gracefully."""
        from reveal.adapters.sqlite.renderer import SqliteRenderer
        from io import StringIO

        # Capture stderr
        old_stderr = sys.stderr
        sys.stderr = captured_output = StringIO()

        error = FileNotFoundError("Database not found")
        SqliteRenderer.render_error(error)

        sys.stderr = old_stderr
        output = captured_output.getvalue()

        self.assertIn('Error accessing SQLite database', output)


class TestSQLiteAdapterEdgeCases(unittest.TestCase):
    """Test edge cases and special scenarios."""

    def test_empty_database(self):
        """Should handle database with no tables."""
        temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        temp_db.close()
        db_path = temp_db.name

        # Create empty database
        conn = sqlite3.connect(db_path)
        conn.close()

        try:
            adapter = SQLiteAdapter(f"sqlite://{db_path}")
            result = adapter.get_structure()

            self.assertEqual(result['statistics']['tables'], 0)
            self.assertEqual(result['statistics']['views'], 0)
            self.assertEqual(result['statistics']['total_rows'], 0)
            self.assertEqual(len(result['tables']), 0)
        finally:
            os.unlink(db_path)

    def test_table_with_no_indexes(self):
        """Should handle table without indexes."""
        temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        temp_db.close()
        db_path = temp_db.name

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE simple (id INTEGER, name TEXT)")
        cursor.execute("INSERT INTO simple VALUES (1, 'test')")
        conn.commit()
        conn.close()

        try:
            adapter = SQLiteAdapter(f"sqlite://{db_path}/simple")
            result = adapter.get_element('simple')

            self.assertEqual(result['table'], 'simple')
            self.assertEqual(len(result['indexes']), 0)
            self.assertEqual(result['row_count'], 1)
        finally:
            os.unlink(db_path)

    def test_view_inspection(self):
        """Should handle views correctly."""
        temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        temp_db.close()
        db_path = temp_db.name

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE base_table (id INTEGER, value TEXT)")
        cursor.execute("CREATE VIEW test_view AS SELECT id, value FROM base_table WHERE id > 0")
        conn.commit()
        conn.close()

        try:
            adapter = SQLiteAdapter(f"sqlite://{db_path}")
            result = adapter.get_structure()

            # Should list both table and view
            table_names = [t['name'] for t in result['tables']]
            self.assertIn('base_table', table_names)
            self.assertIn('test_view', table_names)

            # View should be marked as type 'view'
            view = next(t for t in result['tables'] if t['name'] == 'test_view')
            self.assertEqual(view['type'], 'view')
        finally:
            os.unlink(db_path)

    def test_special_characters_in_table_name(self):
        """Should handle tables with special characters in names."""
        temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        temp_db.close()
        db_path = temp_db.name

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Use quotes for special characters
        cursor.execute('CREATE TABLE "table-with-dashes" (id INTEGER)')
        cursor.execute('INSERT INTO "table-with-dashes" VALUES (1)')
        conn.commit()
        conn.close()

        try:
            adapter = SQLiteAdapter(f"sqlite://{db_path}")
            result = adapter.get_structure()

            table_names = [t['name'] for t in result['tables']]
            self.assertIn('table-with-dashes', table_names)

            # Should be able to query specific table
            element = adapter.get_element('table-with-dashes')
            self.assertIsNotNone(element)
            self.assertEqual(element['table'], 'table-with-dashes')
        finally:
            os.unlink(db_path)

    def test_connection_cleanup(self):
        """Should clean up connection properly."""
        temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        temp_db.close()
        db_path = temp_db.name

        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()

        try:
            adapter = SQLiteAdapter(f"sqlite://{db_path}")
            _ = adapter.get_structure()

            # Delete adapter, should trigger __del__ and close connection
            del adapter

            # Should be able to delete database file (connection closed)
            os.unlink(db_path)
            self.assertFalse(os.path.exists(db_path))
        except:
            if os.path.exists(db_path):
                os.unlink(db_path)
            raise


if __name__ == '__main__':
    unittest.main()
