"""MySQL database adapter module.

Provides progressive disclosure of MySQL database health, performance,
and configuration through semantic resource exploration.
"""

from .adapter import MySQLAdapter

__all__ = ['MySQLAdapter']
