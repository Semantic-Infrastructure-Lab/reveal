"""Update checking utilities for reveal."""

import os
from datetime import datetime, timedelta


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

    # Opt-out check
    if os.environ.get('REVEAL_NO_UPDATE_CHECK'):
        return

    try:
        # Use unified config system for cache file
        cache_file = get_cache_path('last_update_check')

        # Check if we should update (once per day)
        if cache_file.exists():
            last_check_str = cache_file.read_text(encoding='utf-8').strip()
            try:
                last_check = datetime.fromisoformat(last_check_str)
                if datetime.now() - last_check < timedelta(days=1):
                    return  # Checked recently, skip
            except (ValueError, OSError):
                pass  # Invalid cache, continue with check

        # Check PyPI (using urllib to avoid new dependencies)
        import urllib.request
        import json

        req = urllib.request.Request(
            'https://pypi.org/pypi/reveal-cli/json',
            headers={'User-Agent': f'reveal-cli/{__version__}'}
        )

        with urllib.request.urlopen(req, timeout=1) as response:
            data = json.loads(response.read().decode('utf-8'))
            latest_version = data['info']['version']

        # Update cache file
        cache_file.write_text(datetime.now().isoformat())

        # Compare versions (simple string comparison works for semver)
        if latest_version != __version__:
            # Parse versions for proper comparison
            def parse_version(v):
                return tuple(map(int, v.split('.')))

            try:
                if parse_version(latest_version) > parse_version(__version__):
                    print(f"⚠️  Update available: reveal {latest_version} (you have {__version__})")
                    print("Update available: pip install --upgrade reveal-cli\n")
            except (ValueError, AttributeError):
                pass  # Version comparison failed, ignore

    except Exception:
        # Fail silently - don't interrupt user's workflow
        pass
