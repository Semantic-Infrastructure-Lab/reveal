"""B005: Dead import detector.

Detects import statements that reference modules that don't exist or can't be resolved.
This catches orphaned imports left behind after refactoring.
"""

import ast
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from importlib.util import find_spec

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class B005(BaseRule):
    """Detect imports referencing non-existent modules."""

    code = "B005"
    message = "Import references non-existent or unresolvable module"
    category = RulePrefix.B
    severity = Severity.HIGH
    file_patterns = ['.py']
    version = "1.0.0"

    # Standard library modules that might not resolve via find_spec
    STDLIB_MODULES = {
        'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio',
        'asyncore', 'atexit', 'audioop', 'base64', 'bdb', 'binascii',
        'binhex', 'bisect', 'builtins', 'bz2', 'calendar', 'cgi', 'cgitb',
        'chunk', 'cmath', 'cmd', 'code', 'codecs', 'codeop', 'collections',
        'colorsys', 'compileall', 'concurrent', 'configparser', 'contextlib',
        'contextvars', 'copy', 'copyreg', 'cProfile', 'crypt', 'csv',
        'ctypes', 'curses', 'dataclasses', 'datetime', 'dbm', 'decimal',
        'difflib', 'dis', 'distutils', 'doctest', 'email', 'encodings',
        'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp', 'fileinput',
        'fnmatch', 'fractions', 'ftplib', 'functools', 'gc', 'getopt',
        'getpass', 'gettext', 'glob', 'graphlib', 'grp', 'gzip', 'hashlib',
        'heapq', 'hmac', 'html', 'http', 'idlelib', 'imaplib', 'imghdr',
        'imp', 'importlib', 'inspect', 'io', 'ipaddress', 'itertools',
        'json', 'keyword', 'lib2to3', 'linecache', 'locale', 'logging',
        'lzma', 'mailbox', 'mailcap', 'marshal', 'math', 'mimetypes',
        'mmap', 'modulefinder', 'multiprocessing', 'netrc', 'nis',
        'nntplib', 'numbers', 'operator', 'optparse', 'os', 'ossaudiodev',
        'pathlib', 'pdb', 'pickle', 'pickletools', 'pipes', 'pkgutil',
        'platform', 'plistlib', 'poplib', 'posix', 'posixpath', 'pprint',
        'profile', 'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr',
        'pydoc', 'queue', 'quopri', 'random', 're', 'readline', 'reprlib',
        'resource', 'rlcompleter', 'runpy', 'sched', 'secrets', 'select',
        'selectors', 'shelve', 'shlex', 'shutil', 'signal', 'site',
        'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd',
        'sqlite3', 'ssl', 'stat', 'statistics', 'string', 'stringprep',
        'struct', 'subprocess', 'sunau', 'symtable', 'sys', 'sysconfig',
        'syslog', 'tabnanny', 'tarfile', 'telnetlib', 'tempfile', 'termios',
        'test', 'textwrap', 'threading', 'time', 'timeit', 'tkinter',
        'token', 'tokenize', 'tomllib', 'trace', 'traceback', 'tracemalloc',
        'tty', 'turtle', 'turtledemo', 'types', 'typing', 'unicodedata',
        'unittest', 'urllib', 'uu', 'uuid', 'venv', 'warnings', 'wave',
        'weakref', 'webbrowser', 'winreg', 'winsound', 'wsgiref', 'xdrlib',
        'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zlib',
        # typing extensions
        'typing_extensions', 'TYPE_CHECKING',
        # Common third-party that are often optional
        '__future__',
    }

    def _check_import_statement(self,
                                node: ast.Import,
                                file_path: str,
                                file_dir: Path) -> List[Detection]:
        """Check 'import X' statement for dead imports.

        Args:
            node: AST Import node
            file_path: Path to the file being checked
            file_dir: Directory containing the file

        Returns:
            List of detections for dead imports
        """
        detections = []
        for alias in node.names:
            module_name = alias.name.split('.')[0]
            if not self._module_exists(module_name, file_dir):
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"Import '{alias.name}' references non-existent module",
                    suggestion=f"Remove unused import or install missing package '{module_name}'",
                    context=f"import {alias.name}"
                ))
        return detections

    def _check_from_import_statement(self,
                                     node: ast.ImportFrom,
                                     file_path: str,
                                     file_dir: Path) -> List[Detection]:
        """Check 'from X import Y' statement for dead imports.

        Args:
            node: AST ImportFrom node
            file_path: Path to the file being checked
            file_dir: Directory containing the file

        Returns:
            List of detections for dead imports
        """
        detections = []

        if not node.module:
            return detections

        # Handle relative imports
        if node.level > 0:
            if not self._relative_import_exists(node, file_path):
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"Relative import '{'.' * node.level}{node.module or ''}' cannot be resolved",
                    suggestion="Check that the referenced module exists in the package",
                    context=f"from {'.' * node.level}{node.module or ''} import ..."
                ))
        else:
            # Absolute import
            module_name = node.module.split('.')[0]
            if not self._module_exists(module_name, file_dir):
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"Import from '{node.module}' references non-existent module",
                    suggestion=f"Remove unused import or install missing package '{module_name}'",
                    context=f"from {node.module} import ..."
                ))

        return detections

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """
        Check for imports that reference non-existent modules.

        Args:
            file_path: Path to Python file
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections for dead imports
        """
        detections = []
        file_dir = Path(file_path).parent

        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as e:
            logger.debug(f"Syntax error in {file_path}, skipping B005 check: {e}")
            return detections

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                detections.extend(self._check_import_statement(node, file_path, file_dir))
            elif isinstance(node, ast.ImportFrom):
                detections.extend(self._check_from_import_statement(node, file_path, file_dir))

        return detections

    def _module_exists(self, module_name: str, file_dir: Path) -> bool:
        """Check if a module exists."""
        # Skip stdlib modules
        if module_name in self.STDLIB_MODULES:
            return True

        # Check if it's a local module (file in same directory or package)
        if (file_dir / f"{module_name}.py").exists():
            return True
        if (file_dir / module_name / "__init__.py").exists():
            return True

        # Try to find the module spec
        try:
            spec = find_spec(module_name)
            return spec is not None
        except (ModuleNotFoundError, ValueError, ImportError):
            return False

    def _relative_import_exists(self, node: ast.ImportFrom, file_path: str) -> bool:
        """Check if a relative import can be resolved."""
        file_dir = Path(file_path).parent

        # Go up 'level' directories
        target_dir = file_dir
        for _ in range(node.level - 1):
            target_dir = target_dir.parent

        if node.module:
            # from .foo import bar -> check for foo.py or foo/
            parts = node.module.split('.')
            for part in parts:
                if (target_dir / f"{part}.py").exists():
                    return True
                if (target_dir / part).is_dir():
                    target_dir = target_dir / part
                else:
                    return False
            return True
        else:
            # from . import foo -> check __init__.py exists
            return (target_dir / "__init__.py").exists()
