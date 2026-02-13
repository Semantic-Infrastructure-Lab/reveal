"""Version information for reveal.

This module is separate to avoid circular dependencies with utils.updates.
"""

# Version is read from pyproject.toml at runtime
try:
    from importlib.metadata import version
    __version__ = version("reveal-cli")
except Exception:
    # Fallback for development/editable installs
    __version__ = "0.42.0-dev"
