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

* **Version-keyed by path.** Entries live under
  ``<root>/v<SCHEMA>/<reveal_version>/<namespace>/<key>.pkl``. A reveal upgrade
  or a schema bump lands in a *different* directory, so an old cache is simply
  never read (and old version dirs can be pruned) — a changed serialized shape
  can never be misread as the new shape.
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

import os
import pickle
import tempfile
from pathlib import Path
from typing import Any, Optional

from ..version import __version__

# Bump when the *framework* of a cached artifact changes in a way that the
# per-artifact key can't capture (e.g. the pickle protocol strategy, the path
# layout). Per-artifact shape changes are already covered by keying on
# __version__, so routine dataclass edits between releases do NOT need a bump;
# this is a belt-and-suspenders guard for dev checkouts where __version__ is
# static across shape changes.
CACHE_SCHEMA_VERSION = 1

# Best-effort cap on entries kept per namespace (oldest evicted on write).
_MAX_ENTRIES_PER_NAMESPACE = 64

_DISABLED_VALUES = {"0", "false", "no", "off", ""}


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


def _namespace_dir(namespace: str) -> Path:
    return (
        cache_root()
        / f"v{CACHE_SCHEMA_VERSION}"
        / str(__version__)
        / namespace
    )


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
        ns_dir.mkdir(parents=True, exist_ok=True)
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
    """Best-effort LRU-ish cap: keep the newest ``max_entries``."""
    try:
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
