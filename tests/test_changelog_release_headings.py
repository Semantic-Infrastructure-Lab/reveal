"""Every release tag has its own CHANGELOG heading.

Three release preps overwrote the previous release's `## [X.Y.Z]` heading
instead of adding one above it, so that release's entries silently became part
of the next: 0.94.0 into 0.95.0, 0.103.0 into 0.104.0, 0.124.0 into 0.125.0
(ed4f6a32). 0.124.0's heading was restored; the other two were edited after
the merge, so which entries belong to which release needs a manual split.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Tags before v0.26.0 predate the maintained changelog.
_FIRST_MAINTAINED = (0, 26, 0)
# Merged into the following release's section and edited since; see module docstring.
_KNOWN_MERGED = {'0.94.0', '0.103.0'}


def _release_tags():
    try:
        out = subprocess.run(['git', 'tag', '-l', 'v*'], cwd=ROOT, capture_output=True,
                             text=True, encoding='utf-8', timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    versions = []
    for tag in out.split():
        match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)', tag)
        if match and tuple(map(int, match.groups())) >= _FIRST_MAINTAINED:
            versions.append(tag[1:])
    return versions


def test_every_release_tag_has_a_changelog_heading():
    versions = _release_tags()
    if not versions:
        pytest.skip('no release tags in this checkout (shallow clone)')
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    headed = set(re.findall(r'^## \[(\d+\.\d+\.\d+)\]', changelog, re.MULTILINE))
    missing = sorted(set(versions) - headed - _KNOWN_MERGED)
    assert not missing, (
        f'release tags with no "## [X.Y.Z]" CHANGELOG heading: {missing} -- '
        'a release prep probably renamed the previous heading instead of adding one'
    )
