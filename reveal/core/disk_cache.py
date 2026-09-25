"""Fail-open, version-keyed on-disk cache for expensive deterministic artifacts.

Reveal runs as a fresh process per CLI invocation, so any in-process cache
(e.g. ``I002._graph_cache``, ``treesitter._parse_cache``) dies at exit. The
normal DD/agent pattern is *many* reveal commands against *one* unchanged
checkout, so the same expensive work (parsing the whole tree, building the
import graph) is redone from cold every invocation. This module persists such
artifacts under ``~/.reveal/cache/`` so the 2nd+ command on an unchanged tree
is cheap.

Design invariants (this is correctness-sensitive — reveal's whole value is
trustworthy claims, so a cache must NEVER serve a stale/wrong answer):

* **Build-keyed by path.** Entries live under
  ``<root>/v<SCHEMA>/<reveal_version>-<build>/<namespace>/<key>.pkl``, where
  ``<build>`` fingerprints the code that produced the value: every file of the
  reveal package plus the tree-sitter and language-pack packages (path, mtime,
  size). A reveal upgrade, an edit to a dev checkout (BACK-1294), a
  language-pack swap (BACK-1328) or a schema bump each land in a *different*
  directory, so an old cache is simply never read -- a changed serialized shape
  or a changed extractor can never be served as the new one. Only the
  ``_MAX_BUILDS`` most recently used build dirs are kept.
* **Caller owns the freshness key.** ``get``/``put`` take an opaque ``key`` that
  the caller must derive from everything that affects the value (for the import
  graph: a fingerprint of every source file's path + mtime_ns + size). This
  module makes no assumptions about what "unchanged" means.
* **Fail open, always.** Any error reading, writing, deserializing, or pruning
  is swallowed and treated as a miss / no-op. A broken cache degrades to the
  uncached (correct, slower) path — it never raises and never blocks an answer.
* **Atomic writes.** Values are written to a temp file and ``os.replace``-d into
  place, so a killed process can never leave a half-written entry that later
  deserializes into a wrong value.
* **Kill switch.** ``REVEAL_DISK_CACHE=0`` (or ``false``/``no``/``off``)
  disables all reads and writes. ``REVEAL_CACHE_DIR`` overrides the location.
"""

import functools
import hashlib
import importlib.util
import os
import pickle
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from ..version import __version__

# Bump when the *framework* of a cached artifact changes in a way that the
# per-artifact key can't capture (e.g. the pickle protocol strategy). Code and
# shape changes are already covered by the build fingerprint (which also sees
# a dev checkout's edits), so routine edits do NOT need a bump.
#
# 2026-09-02 (BACK-1266 follow-up): bumped 1 -> 2. ImportsDiskCache's stored
# value changed shape from bare `imports` to `(imports, parse_failed)` --
# without this bump, in a dev checkout (unreleased, __version__ unchanged) a
# pre-existing v1 entry unpacks as `imports, parse_failed = <ImportStatement
# list>`, which raises unless that file happens to have exactly 2 imports.
CACHE_SCHEMA_VERSION = 2

# Best-effort cap on entries kept per namespace (oldest evicted on write).
_MAX_ENTRIES_PER_NAMESPACE = 64

# Build dirs kept under v<SCHEMA>/ (most recently used first). Every edit to a
# dev checkout starts a new build dir, so without a cap they accumulate.
_MAX_BUILDS = 4

# Packages whose code decides what a cached artifact contains: reveal itself,
# walked recursively (extractors, rule tables), and the parser stack, whose
# top-level files (the compiled binding, the grammar registry) change on any
# upgrade. Located via find_spec, so fingerprinting never imports them.
_BUILD_PACKAGES = (("reveal", True), ("tree_sitter", False), ("tree_sitter_language_pack", False))

_DISABLED_VALUES = {"0", "false", "no", "off", ""}

# Build dirs whose mtime this process has already refreshed (see _mark_used).
_used_build_dirs: set = set()


def is_enabled() -> bool:
    """True unless REVEAL_DISK_CACHE is explicitly set to a falsey value."""
    raw = os.environ.get("REVEAL_DISK_CACHE")
    if raw is None:
        return True
    return raw.strip().lower() not in _DISABLED_VALUES


def cache_root() -> Path:
    """Base cache directory (``REVEAL_CACHE_DIR`` overrides ``~/.reveal/cache``)."""
    override = os.environ.get("REVEAL_CACHE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".reveal" / "cache"


def _package_files(package: str, recursive: bool):
    """(relative path, stat) for a package's files, sorted; [] if it is not installed."""
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.origin:
        return []
    root = os.path.dirname(spec.origin)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__") if recursive else []
        for name in filenames:
            if name.endswith((".pyc", ".tmp")):
                continue
            full = os.path.join(dirpath, name)
            found.append((os.path.relpath(full, root), os.stat(full)))
    return sorted(found, key=lambda item: item[0])


@functools.lru_cache(maxsize=1)
def build_fingerprint() -> Optional[str]:
    """Short digest of the code that produces cached values, or None if unknowable.

    Stat-only (no file reads, ~5 ms for ~600 files), computed once per process.
    None disables the cache for this process rather than risk a key that
    misses a code change.
    """
    try:
        hasher = hashlib.sha256()
        for package, recursive in _BUILD_PACKAGES:
            hasher.update(f"{package}\0".encode())
            for rel, st in _package_files(package, recursive):
                hasher.update(f"{rel}\0{st.st_mtime_ns}\0{st.st_size}\0".encode("utf-8", "replace"))
        return hasher.hexdigest()[:12]
    except Exception:
        # Fail open: an unstat-able package means no trustworthy key, so this
        # process runs uncached (correct, slower) rather than risk a stale hit.
        return None


def _build_dir() -> Path:
    fingerprint = build_fingerprint()
    if fingerprint is None:
        raise RuntimeError("build fingerprint unavailable")
    return cache_root() / f"v{CACHE_SCHEMA_VERSION}" / f"{__version__}-{fingerprint}"


def _namespace_dir(namespace: str) -> Path:
    return _build_dir() / namespace


def _entry_path(namespace: str, key: str) -> Path:
    # key is expected to be a hex digest (filesystem-safe); guard anyway.
    safe_key = "".join(c for c in key if c.isalnum() or c in "-_")
    return _namespace_dir(namespace) / f"{safe_key}.pkl"


def get(namespace: str, key: str) -> Optional[Any]:
    """Return the cached value for (namespace, key), or None on miss/any error."""
    if not is_enabled():
        return None
    try:
        path = _entry_path(namespace, key)
        if not path.is_file():
            return None
        with open(path, "rb") as fh:
            return pickle.load(fh)
    except Exception:
        # Corrupt/truncated/incompatible entry, or unreadable dir — treat as a
        # miss. Never let a bad cache surface as an error or a wrong answer.
        return None


def put(namespace: str, key: str, value: Any, max_entries: Optional[int] = None) -> None:
    """Persist value under (namespace, key). Best-effort, never raises.

    ``max_entries`` overrides the namespace's prune cap (default
    ``_MAX_ENTRIES_PER_NAMESPACE``). Whole-project artifacts (one entry per
    scan-root, e.g. I002's import graph) fit comfortably under the default;
    per-file artifacts (e.g. the structure cache, one entry per source file)
    need a cap sized to a real repo's file count, or the namespace thrashes
    and every entry is evicted before it can ever be reused.
    """
    if not is_enabled():
        return
    try:
        ns_dir = _namespace_dir(namespace)
        new_build = not ns_dir.parent.exists()
        ns_dir.mkdir(parents=True, exist_ok=True)
        _mark_used(ns_dir.parent)
        if new_build:
            _prune_builds(ns_dir.parent)
        target = _entry_path(namespace, key)
        # Atomic write: temp file in the same dir + os.replace.
        fd, tmp_name = tempfile.mkstemp(dir=str(ns_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                pickle.dump(value, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_name, str(target))
        except Exception:
            # Clean up the temp file on any failure mid-write.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        _prune(ns_dir, max_entries if max_entries is not None else _MAX_ENTRIES_PER_NAMESPACE)
    except Exception:
        # Read-only home, disk full, race — degrade silently to no caching.
        return


def _prune(ns_dir: Path, max_entries: int) -> None:
    """Best-effort LRU-ish cap: keep the newest ``max_entries``.

    Cheap by default: a namespace under its cap is the overwhelmingly common
    case (every ``put()`` call re-checks), so we count entries via
    ``os.scandir`` (readdir only, no per-entry ``stat``) and bail out the
    moment the running count clears ``max_entries`` — no need to finish
    listing a namespace already known to be over cap. Only when the count
    actually exceeds ``max_entries`` do we pay for the ``stat``-per-entry
    sort needed to evict the oldest ones.
    """
    try:
        over_cap = False
        with os.scandir(ns_dir) as it:
            count = 0
            for entry in it:
                if entry.name.endswith(".pkl"):
                    count += 1
                    if count > max_entries:
                        over_cap = True
                        break
        if not over_cap:
            return
        entries = sorted(
            (p for p in ns_dir.glob("*.pkl")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for stale in entries[max_entries:]:
            try:
                stale.unlink()
            except OSError:
                pass
    except Exception:
        return


def _mark_used(build_dir: Path) -> None:
    """Refresh a build dir's mtime once per process, so pruning keeps the builds
    still in use (two venvs alternating) rather than just the newest-created."""
    if build_dir in _used_build_dirs:
        return
    _used_build_dirs.add(build_dir)
    try:
        os.utime(build_dir)
    except OSError:
        pass


def _prune_builds(current: Path) -> None:
    """Delete all but the ``_MAX_BUILDS`` most recently used build dirs.

    Runs only when a new build dir is created. Every other build dir is a key
    this process can never read, so removing one only costs a cold cache for
    another install that still uses it. Also clears the pre-fingerprint layout
    (``v2/<version>/``), which is just an older sibling.
    """
    try:
        siblings = [p for p in current.parent.iterdir() if p.is_dir() and p != current]
        siblings.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in siblings[_MAX_BUILDS - 1:]:
            shutil.rmtree(stale, ignore_errors=True)
    except Exception:
        # Best-effort housekeeping: an unpruned dir costs disk, never correctness.
        return
