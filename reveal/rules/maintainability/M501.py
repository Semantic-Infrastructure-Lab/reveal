import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)

# Marker patterns: match `# TODO`, `# FIXME`, `# HACK`, `# XXX`
# at the start of a comment anywhere on the line (inline or standalone)
_MARKER_RE = re.compile(r'#\s*(TODO|FIXME|HACK|XXX)\b', re.IGNORECASE)

# Paths that are intentionally full of TODO markers (templates, scaffolds)
_SKIP_PATH_FRAGMENTS = [
    "reveal/templates/",
    "reveal/adapters/demo.py",
]


class M501(BaseRule):
    """Detect unresolved TODO/FIXME/HACK/XXX comment markers."""

    code = "M501"
    message = "Unresolved comment marker"
    category = RulePrefix.M
    severity = Severity.LOW
    file_patterns = ['*']  # Universal: all file types
    version = "1.0.0"

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """
        Scan each line for TODO/FIXME/HACK/XXX comment markers.

        Args:
            file_path: Path to file
            structure: Parsed structure (unused — line-level scan)
            content: File content

        Returns:
            One Detection per matching line
        """
        detections: List[Detection] = []

        try:
            # Skip intentional scaffold/template paths
            normalized = file_path.replace("\\", "/")
            for fragment in _SKIP_PATH_FRAGMENTS:
                if fragment in normalized:
                    return detections

            # Optional: load per-rule ignore patterns from config
            # .reveal.yaml:
            #   rules:
            #     M501:
            #       ignore_patterns: ["remove in v", "intentional"]
            ignore_patterns: List[str] = self.get_threshold("ignore_patterns", []) or []

            for lineno, line in enumerate(content.splitlines(), start=1):
                m = _MARKER_RE.search(line)
                if not m:
                    continue

                marker = m.group(1).upper()
                context = line.strip()

                # Apply ignore patterns — skip if any pattern matches the line
                if any(pat.lower() in context.lower() for pat in ignore_patterns):
                    continue

                detections.append(self.create_detection(
                    file_path=file_path,
                    line=lineno,
                    message=f"{self.message}: {marker}",
                    column=m.start() + 1,
                    suggestion=(
                        f"Resolve or track this {marker} in your issue tracker, "
                        f"then remove the comment."
                    ),
                    context=context,
                ))

        except Exception as e:
            logger.debug(f"M501 check failed on {file_path}: {e}")

        return detections
