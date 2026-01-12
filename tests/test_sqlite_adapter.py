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


if __name__ == '__main__':
    unittest.main()
