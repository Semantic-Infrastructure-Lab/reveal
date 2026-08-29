"""Shared import classification logic (BACK-1190).

Classifies a single import into a bucket based on resolution truth
(BACK-1193's ``resolved`` field) and, only where a language-appropriate list
actually exists, a stdlib name match. A Python stdlib list is never used as
a fallback classifier for other languages -- that was exactly the confident-
wrong failure BACK-1193 found and fixed in ``deps://``. This module is the
one place that logic lives now; ``reveal/adapters/deps.py`` and
``reveal/adapters/imports.py`` both import from here instead of each keeping
their own copy.

Buckets:
    'internal' -- syntactically relative, resolved to a real in-tree file
                  (BACK-1193), or a name matching a local package directory.
    'stdlib'   -- matched a language-appropriate stdlib list (Python's
                  sys.stdlib_module_names, or a syntactic marker like Dart's
                  'dart:' prefix that needs no list).
    'external' -- did not resolve and isn't stdlib; may be a genuine
                  third-party package OR an unresolved local (missing
                  file_index coverage, monorepo/load-path boundary) -- never
                  claim positively which.
    'skip'     -- empty module string, nothing to classify.
"""
import sys
from pathlib import Path
from typing import Optional, Tuple

# Python stdlib module names (Python 3.10+, with fallback set for older versions)
try:
    _STDLIB: frozenset = getattr(sys, 'stdlib_module_names', frozenset())
except Exception:
    # sys.stdlib_module_names is 3.10+; any lookup failure falls back to
    # _STDLIB_FALLBACK below rather than leaving stdlib detection empty.
    _STDLIB = frozenset()

# Common stdlib top-level names as fallback
_STDLIB_FALLBACK = frozenset({
    'abc', 'ast', 'asyncio', 'builtins', 'collections', 'contextlib',
    'copy', 'dataclasses', 'datetime', 'enum', 'functools', 'gc',
    'glob', 'hashlib', 'http', 'importlib', 'inspect', 'io', 'itertools',
    'json', 'logging', 'math', 'multiprocessing', 'operator', 'os',
    'pathlib', 'pickle', 'platform', 're', 'shutil', 'signal', 'socket',
    'sqlite3', 'string', 'struct', 'subprocess', 'sys', 'tempfile',
    'threading', 'time', 'traceback', 'typing', 'unittest', 'urllib',
    'uuid', 'warnings', 'weakref', 'zipfile', 'zlib',
})

KNOWN_PYTHON_STDLIB = _STDLIB | _STDLIB_FALLBACK

# Public field values for imports:// records' 'classification' field
# (BACK-1190). Distinct from the internal bucket names above -- these are
# the corrected-prescription terms: resolution truth first, honest
# "unresolved" instead of a false positive "third_party" claim.
INTRA_PROJECT = 'intra_project'
STDLIB = 'stdlib'
UNRESOLVED = 'unresolved'
UNKNOWN = 'unknown'

_BUCKET_TO_CLASSIFICATION = {
    'internal': INTRA_PROJECT,
    'stdlib': STDLIB,
    'external': UNRESOLVED,
    'skip': UNKNOWN,
}


def local_package_names(base_path: Path) -> frozenset:
    """Return top-level package names local to the scanned directory.

    Includes the directory's own name (for absolute self-imports like
    `from reveal.cli import ...` when scanning the reveal/ dir) and any
    immediate subdirectory that is a Python package (has __init__.py).
    """
    names = {base_path.name}
    try:
        for child in base_path.iterdir():
            if child.is_dir() and (child / '__init__.py').exists():
                names.add(child.name)
    except OSError:
        pass
    return frozenset(names)


def classify_module(
    raw_module: str, is_python_file: bool, local_names: frozenset,
) -> Tuple[str, Optional[str]]:
    """Classify one non-relative, unresolved import (BACK-1193).

    Returns ``(bucket, key)`` where bucket is 'internal', 'stdlib',
    'external', or 'skip' (empty module string — nothing to count), and key
    is the counted name (None for 'internal'/'skip').
    """
    if raw_module.startswith('dart:'):
        return ('stdlib', raw_module)  # syntactic marker, no list needed
    module = raw_module.split('.')[0]
    if not module:
        return ('skip', None)  # nothing to classify
    if module in local_names:
        return ('internal', None)
    if is_python_file and module in KNOWN_PYTHON_STDLIB:
        return ('stdlib', module)
    return ('external', module)


def classify_import(
    module: str, is_relative: bool, resolved: Optional[str],
    is_python_file: bool, local_names: frozenset,
    is_intra: Optional[bool] = None,
) -> str:
    """Classify one import record into the public 'classification' values.

    ``resolved``/``is_relative`` (BACK-1193 resolution truth) take priority
    over any name-based guess -- a resolved in-tree file is 'intra_project'
    regardless of what its module string looks like.

    ``is_intra`` (BACK-1234): the extractor's own
    ``is_intra_project_import`` verdict for languages with a real
    declared-namespace/manifest signal (Go, and C#/Java/Kotlin/PHP given
    ``project_namespaces``). Only consulted to *upgrade* an otherwise-
    'external' (bare-heuristic) verdict to 'intra_project' -- it never
    overrides a 'stdlib' or already-'internal' verdict from ``local_names``,
    which is why Python's own ``is_intra_project_import`` correctly
    returning ``False`` for e.g. ``os`` (a stdlib module, not "unresolved")
    must not downgrade `os`'s classification away from 'stdlib'. ``None``
    (the extractor can't tell, or doesn't implement the method) leaves the
    heuristic's verdict untouched either way.
    """
    if is_relative or resolved:
        return INTRA_PROJECT
    bucket, _key = classify_module(module or '', is_python_file, local_names)
    if bucket == 'external' and is_intra is True:
        return INTRA_PROJECT
    return _BUCKET_TO_CLASSIFICATION[bucket]
