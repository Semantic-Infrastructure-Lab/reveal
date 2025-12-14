"""Python runtime adapter package.

This package provides the python:// URI adapter for runtime inspection:
- adapter.py: Core PythonAdapter class
- bytecode.py: Bytecode checking (stale .pyc detection)
- packages.py: Package management utilities
- modules.py: Module import analysis
- doctor.py: Environment diagnostics
- help.py: Help documentation
"""

from .adapter import PythonAdapter

__all__ = ['PythonAdapter']
