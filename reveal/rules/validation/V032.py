"""V032: release-process gap detection (BACK-1022).

Warns when reveal-cli's git history has run ahead of the latest published
PyPI release for longer than a threshold, so accuracy fixes don't sit
unpublished with zero signal. This is exactly what happened before session
maroon-jewel-0808: ~19 DD-accuracy fixes (BACK-1002-1021) sat merged to
origin/master but unpublished to PyPI for 36+ hours, discovered only by
manually diffing `git log v0.115.0..origin/master` against `pip index
versions reveal-cli`.

Check: resolve the git tag matching the latest version published to PyPI,
then look at commits reachable from origin/master (falling back to HEAD if
no configured remote) but not from that tag. If the oldest such commit is
older than the threshold (default 3 days, REVEAL_RELEASE_GAP_DAYS
overrides), flag it.

Best-effort by design, matching utils/updates.py's network posture:
requires PyPI network access, a local git checkout, and the release tag
being present. Any failure along that path (offline, no git repo, tag not
found locally, PyPI unreachable) means "can't tell" rather than "gap" --
this deliberately returns no detections rather than false-flagging a
maintainer who is simply offline or working from a shallow/tagless clone.

Scope: reveal:// self-check only (internal=True), not applicable to
external user code -- this is reveal's own release hygiene, not a rule for
user codebases.
"""

import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD_DAYS = 3
_PYPI_TIMEOUT_SECONDS = 2


class V032(BaseRule):
    """Warn when unreleased commits have sat ahead of PyPI longer than a threshold."""

    code = "V032"
    message = "Release gap: commits unreleased to PyPI beyond threshold"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for a stale gap between origin/master and the latest PyPI release."""
        if not file_path.startswith('reveal://'):
            return []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return []
        project_root = reveal_root.parent

        latest_published = self._latest_pypi_version()
        if not latest_published:
            return []

        commit, gap_days = self._oldest_unreleased_commit(project_root, latest_published)
        if commit is None:
            return []

        threshold_days = self._threshold_days()
        if gap_days < threshold_days:
            return []

        return [self.create_detection(
            file_path='reveal://',
            line=1,
            message=(f"{gap_days} day(s) of commits unreleased to PyPI "
                     f"(published: {latest_published}, oldest unreleased: {commit})"),
            suggestion=(f"Cut a release (see RELEASING.md) or confirm the gap is "
                        f"intentional -- threshold is {threshold_days}d "
                        f"(REVEAL_RELEASE_GAP_DAYS to override)"),
            context=f"latest PyPI: {latest_published}, gap: {gap_days}d"
        )]

    def _threshold_days(self) -> int:
        try:
            return int(os.environ.get('REVEAL_RELEASE_GAP_DAYS', _DEFAULT_THRESHOLD_DAYS))
        except ValueError:
            return _DEFAULT_THRESHOLD_DAYS

    def _latest_pypi_version(self) -> Optional[str]:
        """Best-effort PyPI lookup -- any failure just means 'can't tell'."""
        try:
            import json
            import urllib.request
            from ...version import __version__

            req = urllib.request.Request(
                'https://pypi.org/pypi/reveal-cli/json',
                headers={'User-Agent': f'reveal-cli/{__version__}'}
            )
            with urllib.request.urlopen(req, timeout=_PYPI_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode('utf-8'))['info']['version']
        except Exception:
            return None

    def _oldest_unreleased_commit(self, project_root, published_version):
        """Return (short_hash, age_in_days) for the oldest commit not yet released, or (None, 0)."""
        tag = self._resolve_release_tag(project_root, published_version)
        if tag is None:
            return None, 0

        ref = 'origin/master' if self._ref_exists(project_root, 'origin/master') else 'HEAD'

        log = subprocess.run(
            ['git', 'log', f'{tag}..{ref}', '--format=%H %cI'],
            cwd=project_root, capture_output=True, text=True
        )
        if log.returncode != 0 or not log.stdout.strip():
            return None, 0

        # git log is newest-first; the last line is the oldest unreleased commit.
        oldest_line = log.stdout.strip().splitlines()[-1]
        commit_hash, commit_iso = oldest_line.split(' ', 1)
        try:
            commit_dt = datetime.fromisoformat(commit_iso)
        except ValueError:
            return None, 0
        gap_days = (datetime.now(timezone.utc) - commit_dt).days
        return commit_hash[:8], gap_days

    def _resolve_release_tag(self, project_root, published_version) -> Optional[str]:
        for candidate in (f'v{published_version}', published_version):
            if self._ref_exists(project_root, candidate):
                return candidate
        return None

    def _ref_exists(self, project_root, ref: str) -> bool:
        result = subprocess.run(
            ['git', 'rev-parse', '--verify', '--quiet', ref],
            cwd=project_root, capture_output=True, text=True
        )
        return result.returncode == 0
