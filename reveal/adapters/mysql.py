"""MySQL database adapter (mysql://) - refactored to use modular architecture.

This module now delegates to specialized sub-modules for better maintainability:
- mysql/connection.py - Connection management and credential resolution
- mysql/health.py - Health metrics calculation
- mysql/performance.py - Performance analysis and InnoDB monitoring
- mysql/replication.py - Replication status monitoring
- mysql/storage.py - Storage analysis
- mysql/adapter.py - Main MySQLAdapter orchestrator

Architecture improvements:
- Reduced god module from 1,233 lines to ~600 lines in adapter.py
- Clear separation of concerns across modules
- Each module <300 lines for better readability
- Easier to test individual components
"""

# Re-export MySQLAdapter from the mysql package
from .mysql.adapter import MySQLAdapter

__all__ = ['MySQLAdapter']
