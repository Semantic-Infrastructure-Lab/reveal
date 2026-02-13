"""Bytecode checking utilities for Python adapter."""

from pathlib import Path
from typing import Any, Dict, List, Set


# Directories to skip by default in bytecode checking
BYTECODE_SKIP_DIRS: Set[str] = {
    '.cache', '.venv', 'venv', '.env', 'env',
    'node_modules', '.git',
    '.tox', '.nox', '.pytest_cache', '.mypy_cache',
    'site-packages', 'dist-packages',
    '.eggs', '*.egg-info',
}


def pyc_to_source(pyc_file: Path) -> Path:
    """Convert .pyc file path to corresponding .py file path.

    Args:
        pyc_file: Path to .pyc file

    Returns:
        Path to corresponding .py file
    """
    # Example: __pycache__/module.cpython-310.pyc -> module.py
    if "__pycache__" in pyc_file.parts:
        parent = pyc_file.parent.parent
        # Remove cpython-XXX suffix and .pyc extension
        name = pyc_file.stem.split(".")[0]
        return parent / f"{name}.py"

    # Old style: module.pyc -> module.py
    return pyc_file.with_suffix(".py")


def _check_old_style_pyc(pyc_file: Path) -> Dict[str, Any]:
    """Check if pyc file is old Python 2 style (not in __pycache__)."""
    return {
        "type": "old_style_pyc",
        "severity": "info",
        "file": str(pyc_file),
        "problem": "Python 2 style .pyc file (should be in __pycache__)",
        "fix": f"rm {pyc_file}",
    }


def _check_orphaned_bytecode(pyc_file: Path) -> Dict[str, Any]:
    """Check if pyc file has no corresponding .py file."""
    return {
        "type": "orphaned_bytecode",
        "severity": "info",
        "pyc_file": str(pyc_file),
        "problem": "No matching .py file found",
        "fix": f"rm {pyc_file}",
    }


def _check_stale_bytecode(py_file: Path, pyc_file: Path) -> Dict[str, Any]:
    """Check if pyc file is newer than source (stale bytecode)."""
    return {
        "type": "stale_bytecode",
        "severity": "warning",
        "file": str(py_file),
        "pyc_file": str(pyc_file),
        "problem": ".pyc file is NEWER than source (stale bytecode)",
        "source_mtime": py_file.stat().st_mtime,
        "pyc_mtime": pyc_file.stat().st_mtime,
        "fix": f"rm {pyc_file}",
    }


def _build_bytecode_summary(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build summary statistics for bytecode issues."""
    return {
        "total": len(issues),
        "warnings": len([i for i in issues if i["severity"] == "warning"]),
        "info": len([i for i in issues if i["severity"] == "info"]),
        "errors": len([i for i in issues if i["severity"] == "error"]),
    }


def check_bytecode(root_path: str = ".") -> Dict[str, Any]:
    """Check for bytecode issues (stale .pyc files, orphaned bytecode, etc.).

    Args:
        root_path: Root directory to scan

    Returns:
        Dict with issues found
    """
    issues: List[Dict[str, Any]] = []
    root = Path(root_path)

    def should_skip(path: Path) -> bool:
        """Check if path should be skipped based on directory patterns."""
        parts = path.parts
        for part in parts:
            # Check exact matches
            if part in BYTECODE_SKIP_DIRS:
                return True
            # Check wildcard patterns (e.g., *.egg-info)
            for pattern in BYTECODE_SKIP_DIRS:
                if '*' in pattern:
                    from fnmatch import fnmatch
                    if fnmatch(part, pattern):
                        return True
        return False

    try:
        # Find all .pyc files
        for pyc_file in root.rglob("**/*.pyc"):
            # Skip directories that are typically not user code
            if should_skip(pyc_file):
                continue

            # Skip if not in __pycache__ (old Python 2 style)
            if "__pycache__" not in pyc_file.parts:
                issues.append(_check_old_style_pyc(pyc_file))
                continue

            # Get corresponding .py file
            py_file = pyc_to_source(pyc_file)

            if not py_file.exists():
                issues.append(_check_orphaned_bytecode(pyc_file))
            elif pyc_file.stat().st_mtime > py_file.stat().st_mtime:
                issues.append(_check_stale_bytecode(py_file, pyc_file))

    except Exception as e:
        return {"error": f"Failed to scan for bytecode issues: {str(e)}", "status": "error"}

    return {
        "status": "issues_found" if issues else "clean",
        "issues": issues,
        "summary": _build_bytecode_summary(issues),
    }
