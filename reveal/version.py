"""Version information for reveal.

This module is separate to avoid circular dependencies with utils.updates.
"""

from pathlib import Path

# Root of the package actually running this code -- same resolution
# pattern cli/parser.py's _PACKAGE_DIR uses for --version's path display
# (BACK-1014).
_PACKAGE_DIR = Path(__file__).resolve().parent


def _resolve_version() -> str:
    """Resolve the version of the distribution that owns this running code.

    ``importlib.metadata.version("reveal-cli")`` returns the FIRST
    same-named distribution found while scanning ``sys.path`` -- if a
    stale dist-info/egg-info from an old install (e.g. a leftover
    ``pip install -e`` from a prior version) is still present anywhere on
    sys.path, it can silently win over the one that matches the code
    actually executing. Because Python inserts '' (cwd) into sys.path,
    that scan order -- and therefore the reported version -- becomes
    cwd-dependent (BACK-1126): the SAME installed entrypoint reports
    different versions depending on where it's run from, and that value
    also propagates into --provenance's execution.reveal_version, breaking
    chain-of-custody for DD/agent consumers.

    Fix: read the dist-info/egg-info that sits directly next to this
    file's own directory (the actual install root), instead of scanning
    sys.path by name. ``importlib.metadata.distributions()`` still only
    scans sys.path -- it would have the same cwd-dependent blind spot as
    ``version()`` when the install root itself isn't on sys.path (as is
    the case for editable installs redirected via a MetaPathFinder rather
    than a plain sys.path entry) -- so this looks the metadata up directly
    from disk instead.
    """
    try:
        from importlib.metadata import PathDistribution
        install_root = _PACKAGE_DIR.parent
        candidates = sorted(install_root.glob('reveal_cli*.egg-info')) + \
            sorted(install_root.glob('reveal_cli*.dist-info'))
        for path in candidates:
            dist = PathDistribution(path)
            if dist.metadata.get('Name') == 'reveal-cli':
                return dist.version
    except Exception:
        pass

    # No physical match -- fall back to the old name-based lookup so a
    # working install is never turned into a hard failure.
    try:
        from importlib.metadata import version
        return version("reveal-cli")
    except Exception:
        # Fallback for development/editable installs
        return "0.42.0-dev"


__version__ = _resolve_version()
