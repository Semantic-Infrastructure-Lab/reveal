"""Update checking utilities for reveal."""

import os
from datetime import datetime, timedelta


def _parse_version(v: str) -> tuple:
    """Parse a version string into a tuple of ints for comparison."""
    return tuple(map(int, v.split('.')))


def _is_update_recent(cache_file) -> bool:
    """Return True if an update check was performed in the last 24 hours."""
    if not cache_file.exists():
        return False
    try:
        last_check = datetime.fromisoformat(cache_file.read_text(encoding='utf-8').strip())
        return datetime.now() - last_check < timedelta(days=1)
    except ValueError:
        return False


def _print_update_notice(latest: str, current: str) -> None:
    """Print an update notice if latest > current."""
    if latest == current:
        return
    try:
        if _parse_version(latest) > _parse_version(current):
            print(f"⚠️  Update available: reveal {latest} (you have {current})")
            print("Update available: pip install --upgrade reveal-cli\n")
    except (ValueError, AttributeError):
        pass


def check_for_updates():
    """Check PyPI for newer version (once per day, non-blocking).

    - Checks at most once per day (cached in ~/.cache/reveal/last_update_check)
    - 1-second timeout (doesn't slow down CLI)
    - Fails silently (no errors shown to user)
    - Opt-out: Set REVEAL_NO_UPDATE_CHECK=1 environment variable
    """
    # Import from version module (separate to avoid circular dependencies)
    from ..version import __version__
    from ..config import get_cache_path

    if os.environ.get('REVEAL_NO_UPDATE_CHECK'):
        return

    try:
        import urllib.request
        import json

        cache_file = get_cache_path('last_update_check')
        if _is_update_recent(cache_file):
            return

        req = urllib.request.Request(
            'https://pypi.org/pypi/reveal-cli/json',
            headers={'User-Agent': f'reveal-cli/{__version__}'}
        )
        with urllib.request.urlopen(req, timeout=1) as response:
            latest_version = json.loads(response.read().decode('utf-8'))['info']['version']

        cache_file.write_text(datetime.now().isoformat())
        _print_update_notice(latest_version, __version__)

    except Exception:
        pass
