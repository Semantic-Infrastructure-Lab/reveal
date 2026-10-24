"""Shared import classification logic (BACK-1190).

Classifies a single import into a bucket based on resolution truth
(BACK-1193's ``resolved`` field) and, only where a language-appropriate list
actually exists, a stdlib name match. A Python stdlib list is never used as
a fallback classifier for other languages -- that was exactly the confident-
wrong failure BACK-1193 found and fixed in ``deps://``. This module is the
one place that logic lives now; ``reveal/adapters/deps.py`` and
``reveal/adapters/imports.py`` both import from here instead of each keeping
their own copy. ``package_table`` counts the buckets over a whole import listing:
the deps:// dashboard's package table and imports://?external (BACK-1054).

Buckets:
    'internal' -- syntactically relative, resolved to a real in-tree file
                  (BACK-1193), or a name matching a local package directory.
    'stdlib'   -- matched the language's ``stdlib_key`` rule from the
                  conventions profile (Python's sys.stdlib_module_names, Go's
                  closed root list, Rust std/core/alloc, java./javax., Node
                  builtins, ...) or a syntactic marker like Dart's 'dart:'.
                  A language with no rule never yields 'stdlib'.
    'external' -- did not resolve and isn't stdlib; may be a genuine
                  third-party package OR an unresolved local (missing
                  file_index coverage, monorepo/load-path boundary) -- never
                  claim positively which.
    'skip'     -- empty module string, nothing to classify.
"""
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...conventions import conventions_for, family_for_path
from ...utils.path_utils import _language_for_path, to_relative_display

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
    raw_module: str, family: str, local_names: frozenset,
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
    stdlib_key = conventions_for(family).stdlib_key
    key = stdlib_key(raw_module) if stdlib_key else None
    # local_names is Python-shaped (the scanned dir's own name + __init__.py
    # packages), so outside Python it is really "the dir's name": scanning
    # `src/main/java` must not turn every `java.util.*` import internal.
    if key and family != 'python':
        return ('stdlib', key)
    if module in local_names:
        return ('internal', None)
    if key:
        return ('stdlib', key)
    return ('external', module)


def classify_import(
    module: str, is_relative: bool, resolved: Optional[str],
    family: str, local_names: frozenset,
    is_intra: Optional[bool] = None,
) -> str:
    """Classify one import record into the public 'classification' values.

    ``family`` is the language family slug (``conventions.family_for_path``).

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
    bucket, _key = classify_module(module or '', family, local_names)
    if bucket == 'external' and is_intra is True:
        return INTRA_PROJECT
    return _BUCKET_TO_CLASSIFICATION[bucket]


def _tally_import(
    imp: Dict[str, Any], family: str, local_names: frozenset,
    external_counts: Counter, stdlib_counts: Counter,
    external_languages: Optional[Dict[str, set]] = None,
    language: Optional[str] = None,
) -> bool:
    """Classify+count one import; returns True if it counts as internal.

    BACK-1262: *external_languages* accumulates which source language each
    unresolved package was imported from, so a mixed-stack repo's table can say
    whether `react` came from npm and `pydantic` from Python instead of
    interleaving both in one usage-sorted list with no way to tell.
    """
    if imp.get('is_relative') or imp.get('resolved'):
        return True  # syntactically relative, or resolved in-tree (BACK-1193)
    bucket, key = classify_module(imp.get('module') or '', family, local_names)
    if bucket == 'external' and imp.get('classification') == INTRA_PROJECT:
        # BACK-1236: imports://'s own is_intra_project_import verdict (BACK-1234,
        # declared-namespace matching for Go/C#/Java/Kotlin/PHP) upgraded this
        # import past the name-only heuristic above -- honor that here too,
        # rather than still tallying it as an external package.
        return True
    if key is None:  # 'internal' or 'skip': nothing is counted by name
        return bucket == 'internal'
    if bucket == 'stdlib':
        stdlib_counts[key] += 1
    elif bucket == 'external':
        external_counts[key] += 1
        if external_languages is not None and language:
            external_languages.setdefault(key, set()).add(language)
    return bucket == 'internal'


def package_table(files: Dict[str, List[Dict[str, Any]]], base_path: Path) -> Dict[str, Any]:
    """Derive package counts and top importers from an import listing (imports://'s default
    view ``files``: file -> formatted import records). Moved from deps:// (BACK-1054), whose
    text renderer was its only reader; imports://?external now answers it as JSON.

    BACK-1193: this classifier used to be Python-only in three ways — a
    ``__init__.py``-based local-package heuristic, an unconditional check
    against Python's own stdlib list, and a dot-only module split — applied
    unconditionally to all 18 languages reveal supports. On Ruby it reported
    local files and stdlib modules as "third-party" (`open3`, `fileutils`)
    and manufactured a bogus stdlib count from name collisions with Python
    (`json`, `socket`, ...). Fixed by classifying on resolution truth first:
    ``imports://``'s ``resolved`` field (BACK-1193, real in-tree file or
    None from ``resolve_import()``) is now the primary signal, with the
    ``__init__.py`` heuristic kept only as a fallback for imports resolution
    could not settle. Python-list stdlib is only ever checked for Python
    files — never fall back to Python's list for a non-Python import (task's
    own rule). Dart is the one other language classified as stdlib, because
    its ``dart:`` import prefix (`dart:async`, `dart:io`, ...) is a
    syntactic marker, not a name lookup that could collide the way a bare
    list-membership check would — same rule, no list needed.
    """
    local_names = local_package_names(base_path)
    external_counts: Counter = Counter()
    external_languages: Dict[str, set] = {}
    stdlib_counts: Counter = Counter()
    relative_count = 0
    importer_counts: Counter = Counter()
    total_imports = 0

    for filepath, imports in files.items():
        if not isinstance(imports, list):
            continue
        importer_counts[filepath] += len(imports)
        total_imports += len(imports)
        family = family_for_path(filepath)
        language = _language_for_path(Path(filepath))
        for imp in imports:
            if _tally_import(
                imp, family, local_names, external_counts, stdlib_counts,
                external_languages=external_languages, language=language,
            ):
                relative_count += 1

    # Top importers as relative paths (BACK-1194: shared resolve()-aware
    # helper — see to_relative_display()'s docstring for why the old
    # lexical-only relative_to() let absolute paths leak through on
    # relative CLI targets)
    top_importers = []
    for fp, count in importer_counts.most_common():
        rel = to_relative_display(fp, base_path)
        top_importers.append({'file': rel, 'count': count})

    return {
        'total_imports': total_imports,
        'total_files': len(files),
        'relative_count': relative_count,
        'external_packages': external_counts.most_common(),
        'external_package_languages': {
            pkg: sorted(langs) for pkg, langs in external_languages.items()
        },
        'stdlib_packages': stdlib_counts.most_common(),
        'top_importers': top_importers,
    }
