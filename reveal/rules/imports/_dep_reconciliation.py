"""Shared helpers for I007/I008 (BACK-1191): declared-vs-imported dependency
reconciliation.

Leading underscore keeps this out of RuleRegistry's auto-discovery (which
matches ``^[A-Z]+\\d+$`` filenames only) -- this is plumbing, not a rule.

Deliberately narrow scope for this first pass, chosen from what the
per-language manifest inventories (BACK-1189) actually support soundly:

  Python  -- pyproject.toml/requirements.txt: I007 + I008
  Rust    -- Cargo.toml [dependencies] tables (direct only): I007 + I008

Ruby has a manifest inventory too (_ruby_gem_inventory, BACK-1189), but it's
not wired into I007/I008 here:
  - I007 (declared-but-unused) would be unsound: Gemfile.lock's GEM specs
    are the *resolved* dependency graph (direct + transitive), not what the
    Gemfile itself declares directly -- flagging a transitive gem the app
    never requires directly is expected, not a real finding.
  - I008 (imported-but-undeclared) is sound in principle against that same
    resolved set, but reveal has no vetted Ruby stdlib require-name list
    yet (`require 'net/http'`, `require 'digest/md5'` are stdlib but
    namespaced, so a path-shape heuristic misfires) -- needs a real list
    first, not a guess.

Go/JS-TS/PHP/C# are a further-out follow-up (no declared-dependency
inventory exists for them yet -- see BACK-1191's language-matrix note);
adding one is the same shape as Python/Rust's existing inventory functions.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Callable, FrozenSet, Set

from ...analyzers.imports.base import get_extractor
from ...utils.path_utils import _walk_code_files

# ---------------------------------------------------------------------------
# Python: known PyPI distribution-name <-> top-level-import-name mismatches.
#
# _normalize_dist_name() (python.py) already folds hyphen/underscore/dot
# variation together (e.g. ``flask-sqlalchemy`` == ``flask_sqlalchemy``), so
# this table only needs mismatches that survive that normalization --
# genuinely different strings. Deliberately small and well-known (the same
# shape tools like ``deptry``/``pipreqs`` maintain), not exhaustive: absence
# from this table means "no signal", not "confirmed no mismatch" -- an
# unlisted mismatch stays a false negative (silently not flagged), never a
# false positive, matching BACK-1189's "under-classify rather than guess"
# stance for both directions.
# ---------------------------------------------------------------------------
PY_DIST_TO_IMPORT_ALIASES = {
    'pillow': 'pil',
    'pyyaml': 'yaml',
    'beautifulsoup4': 'bs4',
    'python-dateutil': 'dateutil',
    'python-dotenv': 'dotenv',
    'scikit-learn': 'sklearn',
    'scikit-image': 'skimage',
    'opencv-python': 'cv2',
    'opencv-python-headless': 'cv2',
    'opencv-contrib-python': 'cv2',
    'protobuf': 'google',
    'grpcio': 'grpc',
    'attrs': 'attr',
    'msgpack-python': 'msgpack',
    'pyjwt': 'jwt',
    'pytest-mock': 'pytest_mock',
    'pycrypto': 'crypto',
    'pycryptodome': 'crypto',
    # Found live dogfooding this rule against reveal's own pyproject.toml
    # (BACK-1191) -- both false-flagged before being added here.
    'dnspython': 'dns',
    'python-whois': 'whois',
}
PY_IMPORT_TO_DIST_ALIASES = {v: k for k, v in PY_DIST_TO_IMPORT_ALIASES.items()}


def _fold_hyphen_underscore(name: str) -> str:
    """Rust crate-identifier convention: ``Cargo.toml``'s ``my-crate`` is
    ``use``d as ``my_crate``. A plain module-level function (not a lambda)
    so its identity is stable across calls -- required for
    ``_scan_project_imports``'s ``lru_cache`` to actually hit."""
    return name.replace('-', '_')


@lru_cache(maxsize=64)
def _scan_project_imports(
    root: Path, extensions: FrozenSet[str], normalize: Callable[[str], str], sep: str
) -> FrozenSet[str]:
    """Every normalized top-level module/crate identifier imported anywhere
    (absolute imports only -- relative ones are unambiguously intra-project
    and carry no dependency signal) by a file with one of *extensions* under
    *root*. Cached per (root, extensions, normalize, sep): a full-project
    import scan, the same cost class as I002's cached project-wide import
    graph, and paid at most once per process for a given project (I007 only
    triggers on a manifest file, typically one per project per `check` run).
    """
    names: Set[str] = set()
    for file_path in _walk_code_files(root):
        if file_path.suffix.lower() not in extensions:
            continue
        extractor = get_extractor(file_path)
        if extractor is None:
            continue
        try:
            imports = extractor.extract_imports(file_path)
        except Exception:
            continue
        if getattr(extractor, 'parse_failed', False):
            continue
        for stmt in imports:
            if getattr(stmt, 'is_relative', False) or getattr(stmt, 'level', 0) > 0:
                continue
            top_level = stmt.module_name.split(sep)[0]
            if top_level:
                names.add(normalize(top_level))
    return frozenset(names)


def _raw_python_external_names(project_root: Path) -> FrozenSet[str]:
    """Declared dependency names in their ORIGINAL (unnormalized) manifest
    spelling -- I007 wants to report ``PyYAML``, not the normalized
    ``pyyaml``, in its detection message."""
    from ...analyzers.imports.python import _parse_requirement_names, _parse_pyproject_dependency_names

    names: Set[str] = set()
    names.update(_parse_requirement_names(project_root / 'requirements.txt'))
    names.update(_parse_pyproject_dependency_names(project_root / 'pyproject.toml'))
    return frozenset(names)


def python_declared_unused(project_root: Path) -> FrozenSet[str]:
    """Declared external dependency names (raw manifest spelling) never
    imported anywhere under *project_root* (I007)."""
    from ...analyzers.imports.python import _normalize_dist_name

    raw_names = _raw_python_external_names(project_root)
    if not raw_names:
        return frozenset()
    imported = _scan_project_imports(project_root, frozenset({'.py'}), _normalize_dist_name, '.')
    unused = set()
    for raw_name in raw_names:
        norm = _normalize_dist_name(raw_name)
        alias = PY_DIST_TO_IMPORT_ALIASES.get(norm)
        if norm in imported or (alias and alias in imported):
            continue
        unused.add(raw_name)
    return frozenset(unused)


def _raw_rust_dependency_names(crate_root: Path) -> FrozenSet[str]:
    """Dependency table keys straight out of Cargo.toml, original spelling."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore  # Python < 3.11 fallback

    try:
        with open(crate_root / 'Cargo.toml', 'rb') as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return frozenset()
    names: Set[str] = set()
    for table_name in ('dependencies', 'dev-dependencies', 'build-dependencies'):
        table = data.get(table_name) or {}
        if isinstance(table, dict):
            names.update(table.keys())
    return frozenset(names)


def rust_declared_unused(crate_root: Path) -> FrozenSet[str]:
    """Declared [dependencies]/[dev-dependencies]/[build-dependencies] crate
    names (Cargo.toml key spelling, hyphens intact) never ``use``d anywhere
    under *crate_root* (I007)."""
    from ...analyzers.imports.rust import _rust_crate_inventory

    raw_names = _raw_rust_dependency_names(crate_root)
    if not raw_names:
        return frozenset()
    _, external_identifiers = _rust_crate_inventory(crate_root)
    used_identifiers = _scan_project_imports(
        crate_root, frozenset({'.rs'}), _fold_hyphen_underscore, '::'
    )
    unused = set()
    for raw_name in raw_names:
        identifier = raw_name.replace('-', '_')
        if identifier not in external_identifiers:
            continue  # a path/workspace dep _rust_crate_inventory classified as local
        if identifier not in used_identifiers:
            unused.add(raw_name)
    return frozenset(unused)
