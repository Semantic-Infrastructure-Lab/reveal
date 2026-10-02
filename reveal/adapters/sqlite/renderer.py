"""Renderer for SQLite adapter results."""

from reveal.rendering import TypeDispatchRenderer


class SqliteRenderer(TypeDispatchRenderer):
    """Renderer for SQLite database inspection results.

    Uses TypeDispatchRenderer for automatic routing to _render_{type}() methods.
    """

    @staticmethod
    def _render_sqlite_database(result: dict) -> None:
        """Render SQLite database overview."""
        print(f"SQLite Database: {result['path']}")
        print(f"Version: {result['sqlite_version']}")
        print(f"Size: {result['size']}")
        print()

        config = result['configuration']
        print("Configuration:")
        print(f"  Page Size: {config['page_size']}")
        print(f"  Page Count: {config['page_count']}")
        print(f"  Journal Mode: {config['journal_mode']}")
        print(f"  Encoding: {config['encoding']}")
        print(f"  Foreign Keys: {'Enabled' if config['foreign_keys_enabled'] else 'Disabled'}")
        print()

        stats = result['statistics']
        print("Statistics:")
        print(f"  Tables: {stats['tables']}")
        print(f"  Views: {stats['views']}")
        print(f"  Total Rows: {stats['total_rows']:,}")
        print(f"  Foreign Keys: {stats['foreign_keys']}")
        print()

        print("Tables:")
        for table in result['tables']:
            if table['type'] == 'table':
                print(f"  📋 {table['name']} ({table['rows']:,} rows, {table['columns']} columns, {table['indexes']} indexes)")
            else:  # view
                print(f"  👁️  {table['name']} (view, {table['columns']} columns)")
        print()

        print("Next Steps:")
        for step in result['next_steps']:
            print(f"  {step}")

    @staticmethod
    def _render_table_columns(columns: list) -> None:
        """Render table columns."""
        print(f"Columns ({len(columns)}):")
        for col in columns:
            pk = " [PK]" if col['primary_key'] else ""
            null = " NULL" if col['nullable'] else " NOT NULL"
            default = f" DEFAULT {col['default']}" if col['default'] else ""
            print(f"  • {col['name']}: {col['type']}{pk}{null}{default}")
        print()

    @staticmethod
    def _render_table_indexes(indexes: list) -> None:
        """Render table indexes."""
        if not indexes:
            return
        print(f"Indexes ({len(indexes)}):")
        for idx in indexes:
            unique = " [UNIQUE]" if idx['unique'] else ""
            cols = ', '.join(idx['columns'])
            print(f"  • {idx['name']}{unique} ({cols})")
        print()

    @staticmethod
    def _render_table_foreign_keys(foreign_keys: list) -> None:
        """Render table foreign keys."""
        if not foreign_keys:
            return
        print(f"Foreign Keys ({len(foreign_keys)}):")
        for fk in foreign_keys:
            print(f"  • {fk['column']} → {fk['references_table']}.{fk['references_column']}")
            print(f"    ON DELETE {fk['on_delete']}, ON UPDATE {fk['on_update']}")
        print()

    @staticmethod
    def _render_sqlite_table(result: dict) -> None:
        """Render table details."""
        print(f"Table: {result['table']}")
        print(f"Database: {result['database']}")
        print(f"Row Count: {result['row_count']:,}")
        print()

        # Render sections
        SqliteRenderer._render_table_columns(result['columns'])
        SqliteRenderer._render_table_indexes(result['indexes'])
        SqliteRenderer._render_table_foreign_keys(result['foreign_keys'])

        if result.get('create_statement'):
            print("CREATE Statement:")
            print(result['create_statement'])
            print()

        if result.get('next_steps'):
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  {step}")

    @staticmethod
    def render_check(result: dict, format: str = 'text', **kwargs) -> None:
        """Render ``--check``: the integrity verdict and each finding."""
        from reveal.utils import print_json_result

        if format == 'json':
            print_json_result(result)
            return
        detections = result.get('detections', [])
        print(f"{result['source']}: integrity {'ok' if result['integrity'] else 'FAILED'}")
        if not detections:
            print("✅ No issues found")
            return
        print(f"Found {len(detections)} issue(s)\n")
        for d in detections:
            print(f"  [{d['severity']}] {d['rule']}: {d['message']}")
