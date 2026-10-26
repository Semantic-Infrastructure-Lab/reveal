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

import logging
from dataclasses import dataclass, field

from pathlib import Path
from typing import Callable, Dict, FrozenSet, Iterator, List, NamedTuple, Optional, Sequence, Set, Tuple

from ...analyzers.imports.base import get_extractor
from ...utils.gitignore import gitignore_enabled
from ...utils.path_utils import EVIDENCE, _walk_code_files, to_posix, traversal_failed_warning, failure_of
from ...utils.request_cache import register_request_cache, register_validated_cache
from ...reveal_types import PathFailure

logger = logging.getLogger(__name__)

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
# false positive from the table itself, matching BACK-1189's "under-classify
# rather than guess" stance for both directions. (A source file that did not
# parse can still hide a use: it is reported as skipped, BACK-1857.)
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


class ProjectImports(NamedTuple):
    """What a project-wide import scan found: the imported identifiers, and the source
    files whose imports could not be extracted (their imports are missing from *names*)."""
    names: FrozenSet[str]
    skipped: Tuple[str, ...]


class DeclaredUnused(NamedTuple):
    """Declared-but-never-imported names, and the files the scan could not read.

    A skipped file may be the one that imports a reported name, so a non-empty
    *skipped* means *unused* can contain false positives (I007 reports it)."""
    unused: FrozenSet[str]
    skipped: Tuple[str, ...]


def _fold_hyphen_underscore(name: str) -> str:
    """Rust crate-identifier convention: ``Cargo.toml``'s ``my-crate`` is
    ``use``d as ``my_crate``. A plain module-level function (not a lambda)
    so its identity is stable across calls -- required for
    ``_scan_project_imports``'s cache to actually hit."""
    return name.replace('-', '_')


# {root: {(extensions, normalize, sep): scan}}. A project scan is expensive, so it lives
# while its root's tree is unchanged (request_cache.register_validated_cache, BACK-1572):
# a long-lived MCP host must not answer from the imports it saw on the first request.
_ScanKey = Tuple[FrozenSet[str], Callable[[str], str], str]
_TraversalFailure = PathFailure


@dataclass(frozen=True)
class _ProjectImportFacts:
    imports: ProjectImports
    traversal_failures: Tuple[_TraversalFailure, ...]
    # The walk honours the gitignore switch, so the scan depends on it (BACK-2118).
    gitignore: bool = field(default_factory=gitignore_enabled)
    # A file's extraction failed in reveal's machinery or in its environment, not on its content
    # (``ImportExtraction.cacheable``): unchanged stat, different answer next time (BACK-2139).
    transient: bool = False


_scan_cache: Dict[Path, Dict[_ScanKey, _ProjectImportFacts]] = {}


def _scan_project_imports(
    root: Path, extensions: FrozenSet[str], normalize: Callable[[str], str], sep: str,
    *, on_traversal_failure: Optional[Callable[[_TraversalFailure], None]] = None,
) -> ProjectImports:
    """The cached `_scan_project_imports_uncached` for (root, extensions, normalize, sep)."""
    scans = _scan_cache.setdefault(root, {})
    key = (extensions, normalize, sep)
    if key not in scans or scans[key].gitignore != gitignore_enabled():
        failures: List[OSError] = []
        transient: List[str] = []
        imports = _scan_project_imports_uncached(root, extensions, normalize, sep,
                                               on_error=failures.append, on_transient=transient.append)
        scans[key] = _ProjectImportFacts(imports, tuple(
            failure_of(error)
            for error in failures), transient=bool(transient))
    facts = scans[key]
    if on_traversal_failure is not None:
        for failure in facts.traversal_failures:
            on_traversal_failure(failure)
    return facts.imports


def _evict_root(root: Path) -> None:
    _scan_cache.pop(root, None)


def _evict_incomplete_scans() -> None:
    """Retain useful partial memo within an invocation, never across host requests.

    A scan built with the gitignore switch off is request-local too: the tree stamp that
    validates a kept entry is taken with the default switch, so it cannot see an edit to an
    ignored file (BACK-2118). So is a scan with a file that failed in reveal's machinery or
    its environment: the tree stamp does not change when that failure goes away (BACK-2139).
    """
    for root, scans in tuple(_scan_cache.items()):
        if any(facts.traversal_failures or facts.transient or not facts.gitignore
               for facts in scans.values()):
            _evict_root(root)


register_request_cache(__name__ + '.traversal', _evict_incomplete_scans)
register_validated_cache(__name__, _scan_cache, _evict_root)


def _scan_project_imports_uncached(
    root: Path, extensions: FrozenSet[str], normalize: Callable[[str], str], sep: str,
    *, on_error: Optional[Callable[[OSError], None]] = None,
    on_transient: Optional[Callable[[str], None]] = None,
) -> ProjectImports:
    """Every normalized top-level module/crate identifier imported anywhere
    (absolute imports only -- relative ones are unambiguously intra-project
    and carry no dependency signal) by a file with one of *extensions* under
    *root*. A full-project import scan, the same cost class as I002's project-wide
    import graph; `_scan_project_imports` caches it per (root, extensions, normalize,
    sep) while the tree is unchanged.

    A file whose extraction raises, or whose parse recovered from errors, is recorded in
    ``skipped`` (sorted), not dropped: its imports are missing from (or only partly in)
    ``names``, which the caller must disclose. *on_transient* is called with the path of each
    file whose failure did not come from its content (the analyzer lookup, a grammar that
    could not be loaded, an unreadable file: ``ImportExtraction.cacheable``), so the caller
    does not keep the scan (BACK-2139).
    """
    names: Set[str] = set()
    skipped: Set[str] = set()
    for file_path in _walk_code_files(root, purpose=EVIDENCE, on_error=on_error):
        if file_path.suffix.lower() not in extensions:
            continue
        extractor = get_extractor(file_path)
        if extractor is None:
            continue
        try:
            imports = extractor.extract_imports(file_path)
        except Exception as e:  # boundary-ok: broad-except -- the extractor walks tree-sitter nodes of arbitrary user source (native binding, no enumerable error set); one file must not end the project scan, and the file is returned in ProjectImports.skipped for the rule to report
            logger.warning("_dep_reconciliation.py: skipped %s after %s: %s", file_path, type(e).__name__, e)
            skipped.add(str(file_path))
            continue
        analysis = getattr(extractor, 'analysis', None)
        if on_transient is not None and analysis is not None and not analysis.cacheable:
            on_transient(str(file_path))
        if getattr(extractor, 'parse_failed', False):
            # A recovery parse still yields the imports before the error (BACK-1460), so
            # they count, but the file may hold more it could not see: an unused
            # dependency may be used there, which the rule must say (BACK-1857).
            skipped.add(str(file_path))
        for stmt in imports:
            if getattr(stmt, 'is_relative', False) or getattr(stmt, 'level', 0) > 0:
                continue
            top_level = stmt.module_name.split(sep)[0]
            if top_level:
                names.add(normalize(top_level))
    return ProjectImports(frozenset(names), tuple(sorted(skipped)))


def _raw_python_external_names(project_root: Path) -> FrozenSet[str]:
    """Declared dependency names in their ORIGINAL (unnormalized) manifest
    spelling -- I007 wants to report ``PyYAML``, not the normalized
    ``pyyaml``, in its detection message."""
    from ...analyzers.imports.python import _parse_requirement_names, _parse_pyproject_dependency_names

    names: Set[str] = set()
    names.update(_parse_requirement_names(project_root / 'requirements.txt'))
    names.update(_parse_pyproject_dependency_names(project_root / 'pyproject.toml'))
    return frozenset(names)


def python_declared_unused(
    project_root: Path, *, on_traversal_failure: Optional[Callable[[_TraversalFailure], None]] = None,
) -> DeclaredUnused:
    """Declared external dependency names (raw manifest spelling) never
    imported anywhere under *project_root* (I007)."""
    from ...analyzers.imports.python import _normalize_dist_name

    raw_names = _raw_python_external_names(project_root)
    if not raw_names:
        return DeclaredUnused(frozenset(), ())
    scan = _scan_project_imports(project_root, frozenset({'.py'}), _normalize_dist_name, '.',
                                 on_traversal_failure=on_traversal_failure)
    unused = set()
    for raw_name in raw_names:
        norm = _normalize_dist_name(raw_name)
        alias = PY_DIST_TO_IMPORT_ALIASES.get(norm)
        if norm in scan.names or (alias and alias in scan.names):
            continue
        unused.add(raw_name)
    return DeclaredUnused(frozenset(unused), scan.skipped)


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


def rust_declared_unused(
    crate_root: Path, *, on_traversal_failure: Optional[Callable[[_TraversalFailure], None]] = None,
) -> DeclaredUnused:
    """Declared [dependencies]/[dev-dependencies]/[build-dependencies] crate
    names (Cargo.toml key spelling, hyphens intact) never ``use``d anywhere
    under *crate_root* (I007)."""
    from ...analyzers.imports.rust import _rust_crate_inventory

    raw_names = _raw_rust_dependency_names(crate_root)
    if not raw_names:
        return DeclaredUnused(frozenset(), ())
    _, external_identifiers = _rust_crate_inventory(crate_root)
    scan = _scan_project_imports(
        crate_root, frozenset({'.rs'}), _fold_hyphen_underscore, '::',
        on_traversal_failure=on_traversal_failure,
    )
    unused = set()
    for raw_name in raw_names:
        identifier = raw_name.replace('-', '_')
        if identifier not in external_identifiers:
            continue  # a path/workspace dep _rust_crate_inventory classified as local
        if identifier not in scan.names:
            unused.add(raw_name)
    return DeclaredUnused(frozenset(unused), scan.skipped)


def _directory_disclosure(root: Path, failures: Sequence[_TraversalFailure], language: str) -> Optional[str]:
    warning = traversal_failed_warning(failures, root)
    if warning is None:
        return None
    return (f"I007: {language} project import discovery under {to_posix(root)} is incomplete; "
            f"{warning['message']}; "
            'dependencies reported as unused may be used in omitted inputs')


def _manifest_scan(path: Path) -> Optional[Tuple[Path, _ScanKey]]:
    """Recheck declarations without walking: an old memo is not a reached subject."""
    from ...analyzers.imports.python import _normalize_dist_name

    if path.name not in {'pyproject.toml', 'requirements.txt', 'Cargo.toml'}:
        return None
    root = path.resolve().parent
    if path.name == 'Cargo.toml':
        return ((root, (frozenset({'.rs'}), _fold_hyphen_underscore, '::'))
                if _raw_rust_dependency_names(root) else None)
    if path.name == 'requirements.txt' and (root / 'pyproject.toml').exists():
        return None
    return ((root, (frozenset({'.py'}), _normalize_dist_name, '.'))
            if _raw_python_external_names(root) else None)


def _reached_scan_keys(files: Optional[List[Path]]) -> Iterator[Tuple[Path, _ScanKey]]:
    seen: Set[Tuple[Path, _ScanKey]] = set()
    for path in files or []:
        scan = _manifest_scan(Path(path))
        if scan is not None and scan not in seen:
            seen.add(scan)
            yield scan


def _preload_project_imports(files: Optional[List[Path]]) -> Dict[Path, Dict[_ScanKey, _ProjectImportFacts]]:
    """Build and transfer only the checked manifests' exact language populations."""
    payload: Dict[Path, Dict[_ScanKey, _ProjectImportFacts]] = {}
    for root, key in _reached_scan_keys(files):
        _scan_project_imports(root, *key)
        payload.setdefault(root, {})[key] = _scan_cache[root][key]
    return payload


def get_scan_disclosures(files: Optional[List[Path]] = None) -> List[str]:
    """Read reached directory facts only; never build an index on a cache miss."""
    messages = []
    for root, key in _reached_scan_keys(files):
        facts = _scan_cache.get(root, {}).get(key)
        language = 'Python' if '.py' in key[0] else 'Rust'
        message = _directory_disclosure(root, facts.traversal_failures, language) if facts is not None else None
        if message is not None:
            messages.append(message)
    return messages
