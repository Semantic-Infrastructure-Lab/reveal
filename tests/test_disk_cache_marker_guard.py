"""Guard for BACK-1677: a test that reads the disk cache back cannot depend on the ambient
``REVEAL_DISK_CACHE``.

scripts/ci-local.sh (and the worktree wrapper) export ``REVEAL_DISK_CACHE=0`` for the whole run,
so a test that points ``REVEAL_CACHE_DIR`` at a tmp dir and expects a warm hit passes in plain
pytest and in GitHub CI but fails (or, worse, passes vacuously) under ci-local. The fix is the
``disk_cache`` marker (tests/conftest.py). This file fails a test file that sets the cache dir
without either carrying the marker or naming the switch itself.
"""
import re
from pathlib import Path

import pytest

from reveal.core import disk_cache

pytestmark = pytest.mark.component

TESTS = Path(__file__).parent

# Files that only isolate the cache dir to keep writes out of ~/.reveal and never read it back.
ISOLATION_ONLY = {
    "test_mcp_server.py",  # BACK-1152: keeps put() pruning off the real shared cache
}

_SETS_CACHE_DIR = re.compile(r"REVEAL_CACHE_DIR")
_HANDLES_SWITCH = re.compile(r"REVEAL_DISK_CACHE|mark\.disk_cache")


def unguarded(source: str) -> bool:
    """True if ``source`` points the cache at a dir but neither marks nor names the switch."""
    return bool(_SETS_CACHE_DIR.search(source)) and not _HANDLES_SWITCH.search(source)


def test_every_cache_dir_test_file_handles_the_ambient_switch():
    offenders = [
        p.name
        for p in sorted(TESTS.glob("test_*.py"))
        if p.name != Path(__file__).name
        and p.name not in ISOLATION_ONLY
        and unguarded(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"{offenders} set REVEAL_CACHE_DIR but neither carry @pytest.mark.disk_cache nor set "
        "REVEAL_DISK_CACHE: they pass or fail depending on the ambient switch "
        "(ci-local exports REVEAL_DISK_CACHE=0). Add the marker (BACK-1677)."
    )


def test_negative_control_guard_fires_on_an_unmarked_cache_reader():
    bad = "def test_x(monkeypatch, tmp_path):\n    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path))\n"
    assert unguarded(bad)
    assert not unguarded("pytestmark = pytest.mark.disk_cache\n" + bad)
    assert not unguarded(bad + "    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')\n")


@pytest.mark.disk_cache
def test_marker_enables_cache_whatever_the_ambient_switch_is():
    """Under ci-local / wt-check the ambient value is 0; the marker must have removed it."""
    assert disk_cache.is_enabled()

