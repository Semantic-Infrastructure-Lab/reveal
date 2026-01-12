"""Handler for sqlite:// URIs."""

import sys
import json
from typing import Optional
from argparse import Namespace


def _render_sqlite_result(result: dict, format: str = 'text'):
    """Render SQLite adapter results in human-readable format."""
    if format == 'json':
        print(json.dumps(result, indent=2))
        return

    # Handle different result types
    result_type = result.get('type', 'sqlite_database')

    if result_type == 'sqlite_database':
        # Database overview
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

    elif result_type == 'sqlite_table':
        # Table details
        print(f"Table: {result['table']}")
        print(f"Database: {result['database']}")
        print(f"Row Count: {result['row_count']:,}")
        print()

        print(f"Columns ({len(result['columns'])}):")
        for col in result['columns']:
            pk = " [PK]" if col['primary_key'] else ""
            null = " NULL" if col['nullable'] else " NOT NULL"
            default = f" DEFAULT {col['default']}" if col['default'] else ""
            print(f"  • {col['name']}: {col['type']}{pk}{null}{default}")
        print()

        if result['indexes']:
            print(f"Indexes ({len(result['indexes'])}):")
            for idx in result['indexes']:
                unique = " [UNIQUE]" if idx['unique'] else ""
                cols = ', '.join(idx['columns'])
                print(f"  • {idx['name']}{unique} ({cols})")
            print()

        if result['foreign_keys']:
            print(f"Foreign Keys ({len(result['foreign_keys'])}):")
            for fk in result['foreign_keys']:
                print(f"  • {fk['column']} → {fk['references_table']}.{fk['references_column']}")
                print(f"    ON DELETE {fk['on_delete']}, ON UPDATE {fk['on_update']}")
            print()

        if result.get('create_statement'):
            print("CREATE Statement:")
            print(result['create_statement'])
            print()

        if result.get('next_steps'):
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  {step}")

    else:
        # Unknown result type - just JSON
        print(json.dumps(result, indent=2))


def handle_sqlite(adapter_class: type, resource: str, element: Optional[str], args: Namespace) -> int:
    """Handle sqlite:// URIs.

    Args:
        adapter_class: The SQLite adapter class
        resource: The resource part of the URI (path to database)
        element: Optional element (table name)
        args: Command-line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Reconstruct full URI
        uri = f"sqlite://{resource}"
        if element:
            uri = f"{uri}/{element}"

        # Create adapter
        adapter = adapter_class(uri)

        # Get structure
        result = adapter.get_structure()

        # Render
        format = getattr(args, 'format', 'text')
        _render_sqlite_result(result, format=format)

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Note: SQLite support uses Python's built-in sqlite3 module", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if hasattr(args, 'debug') and args.debug:
            import traceback
            traceback.print_exc()
        return 1
