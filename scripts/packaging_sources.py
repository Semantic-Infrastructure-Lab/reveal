"""Stage package sources away from the checkout before a build (BACK-2321)."""

import shutil
import subprocess
from pathlib import Path


def stage_sources(project_root: Path, dest: Path, commit: bool = True) -> None:
    """Copy tracked and non-ignored working files; optionally supply SCM metadata.

    setuptools_scm adds committed files to distributions. With commit=False this
    instead exercises MANIFEST.in/package-data, as a source archive without Git.
    Both modes keep build staging and egg-info writes out of the real checkout:
    concurrent builds otherwise race version readers and Windows file locks
    (BACK-1895). The no-Git distribution control is BACK-2154.
    """
    listing = subprocess.run(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
        cwd=project_root, capture_output=True, check=True, timeout=30,
    ).stdout.decode('utf-8')
    for rel in filter(None, listing.split('\0')):
        src = project_root / rel
        if src.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
    if not commit:
        return
    git = ['git', '-c', 'user.name=stage', '-c', 'user.email=stage@localhost',
           '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=']
    for args in (['init', '-q'], ['add', '-A'], ['commit', '-q', '--no-verify', '-m', 'stage']):
        # Indexing the full source tree can exceed 30s on hosted Windows runners.
        subprocess.run(git + args, cwd=dest, check=True, capture_output=True, timeout=120)
