"""V014: Token-cost estimate accuracy for AGENT_HELP.md.

Validates that AGENT_HELP.md's documented token cost — its frontmatter
`help_token_estimate`, its body "**Token Cost:**" line, and the `~NK tokens`
literals in `adapters/help.py` that describe it — stay within tolerance of a
computed estimate. Closes the token-cost axis of BACK-388: the number was
hand-typed in 4 places and had drifted to ~12K vs an actual guide size of
~40K, because nothing derived it from the live file.

How it estimates:
    - chars-per-token ~= 4 (standard rough heuristic for English/code text),
      applied to AGENT_HELP.md's content with frontmatter stripped. Same
      order of magnitude as reveal's own hand-typed `help_token_estimate`
      values (QUICK_START.md: 9,988 chars -> ~2,000; AGENT_HELP.md: 164,339
      chars -> ~40,000) — no computed estimator existed before this rule.

Tolerance:
    - A claim is flagged only if it is off by more than 50% from the computed
      estimate (either direction) — generous enough to tolerate normal
      chars/4 rounding noise, tight enough to catch the order-of-magnitude
      drift BACK-388 found.

Scope:
    - reveal/docs/AGENT_HELP.md: frontmatter `help_token_estimate` + the body
      "**Token Cost:**" line.
    - reveal/adapters/help.py: `~NK tokens` literals (code comments excluded —
      those narrate history, not a current claim).
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V014(BaseRule):
    """Validate AGENT_HELP.md's documented token cost against a computed estimate."""

    code = "V014"
    message = "Token-cost estimate mismatch in agent help documentation"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    _CHARS_PER_TOKEN = 4
    _TOLERANCE_RATIO = 0.5  # flag if a claim is <0.5x or >1.5x the computed estimate

    _AGENT_HELP_REL_PATH = 'reveal/docs/AGENT_HELP.md'
    _HELP_PY_REL_PATH = 'reveal/adapters/help.py'

    _BODY_TOKEN_COST_PATTERN = re.compile(
        r'\*\*Token Cost:\*\*\s*~?([\d,]+)\s*tokens', re.IGNORECASE)
    _HELP_PY_LITERAL_PATTERN = re.compile(r'~(\d+)K\s*tokens', re.IGNORECASE)

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check AGENT_HELP.md's token-cost claims against a computed estimate."""
        if not file_path.startswith('reveal://'):
            return []

        detections: List[Detection] = []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections
        project_root = reveal_root.parent

        agent_help_path = project_root / self._AGENT_HELP_REL_PATH
        if not agent_help_path.exists():
            return detections

        actual = self._estimate_tokens(agent_help_path)
        if actual is None:
            return detections

        low = actual * (1 - self._TOLERANCE_RATIO)
        high = actual * (1 + self._TOLERANCE_RATIO)

        detections.extend(self._check_frontmatter(agent_help_path, actual, low, high))
        detections.extend(self._check_body_line(agent_help_path, actual, low, high))

        help_py_path = project_root / self._HELP_PY_REL_PATH
        if help_py_path.exists():
            detections.extend(self._check_help_py_literals(help_py_path, actual, low, high))

        return detections

    def _estimate_tokens(self, agent_help_path: Path) -> Optional[int]:
        """Rough chars/4 token estimate of AGENT_HELP.md's body (frontmatter stripped)."""
        try:
            from reveal.adapters.help import _strip_frontmatter
            content = agent_help_path.read_text(encoding='utf-8')
            body = _strip_frontmatter(content)
            return len(body) // self._CHARS_PER_TOKEN
        except Exception:
            return None

    def _check_frontmatter(self, agent_help_path: Path, actual: int,
                            low: float, high: float) -> List[Detection]:
        try:
            from reveal.adapters.markdown.files import extract_frontmatter
            fm = extract_frontmatter(agent_help_path) or {}
        except Exception:
            return []
        raw = fm.get('help_token_estimate')
        if raw is None:
            return []
        claimed = self._parse_int(str(raw))
        if claimed is None or low <= claimed <= high:
            return []
        return [self.create_detection(
            file_path=self._AGENT_HELP_REL_PATH,
            line=1,
            message=f"Token-cost overclaim/underclaim: frontmatter claims ~{claimed:,}, actual ~{actual:,}",
            suggestion=f"Update {self._AGENT_HELP_REL_PATH} frontmatter help_token_estimate to '~{actual:,}'",
            context=f"Claimed: ~{claimed:,}, computed: ~{actual:,} tokens (chars/4)"
        )]

    def _check_body_line(self, agent_help_path: Path, actual: int,
                          low: float, high: float) -> List[Detection]:
        detections = []
        try:
            lines = agent_help_path.read_text(encoding='utf-8').split('\n')
        except Exception:
            return []
        for i, line in enumerate(lines, 1):
            match = self._BODY_TOKEN_COST_PATTERN.search(line)
            if not match:
                continue
            claimed = self._parse_int(match.group(1))
            if claimed is None or low <= claimed <= high:
                continue
            detections.append(self.create_detection(
                file_path=self._AGENT_HELP_REL_PATH,
                line=i,
                message=f"Token-cost overclaim/underclaim: claims ~{claimed:,}, actual ~{actual:,}",
                suggestion=f"Update {self._AGENT_HELP_REL_PATH} line {i} to '~{actual:,} tokens'",
                context=f"Claimed: ~{claimed:,}, computed: ~{actual:,} tokens (chars/4)"
            ))
        return detections

    def _check_help_py_literals(self, help_py_path: Path, actual: int,
                                 low: float, high: float) -> List[Detection]:
        detections = []
        try:
            lines = help_py_path.read_text(encoding='utf-8').split('\n')
        except Exception:
            return []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue  # narrative comments, not a current claim
            match = self._HELP_PY_LITERAL_PATTERN.search(line)
            if not match:
                continue
            claimed = int(match.group(1)) * 1000
            if low <= claimed <= high:
                continue
            detections.append(self.create_detection(
                file_path=self._HELP_PY_REL_PATH,
                line=i,
                message=f"Token-cost overclaim/underclaim: claims ~{claimed // 1000}K, actual ~{actual:,}",
                suggestion=f"Update {self._HELP_PY_REL_PATH} line {i} to '~{round(actual / 1000)}K tokens'",
                context=f"Claimed: ~{claimed // 1000}K, computed: ~{actual:,} tokens (chars/4)"
            ))
        return detections

    @staticmethod
    def _parse_int(raw: str) -> Optional[int]:
        match = re.search(r'([\d,]+)', raw)
        if not match:
            return None
        try:
            return int(match.group(1).replace(',', ''))
        except ValueError:
            return None
