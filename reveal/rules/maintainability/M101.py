"""M101: File too large detector.

Detects files that exceed recommended size limits.
Large files are hard to navigate, maintain, and consume significant LLM context.
This is a file-level check that warns before processing individual functions.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class M101(BaseRule):
    """Detect files that are too large."""

    code = "M101"
    message = "File is too large"
    category = RulePrefix.M
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Universal: all file types
    version = "1.0.0"

    # Size thresholds (lines)
    THRESHOLD_WARN = 500   # Warning: getting large
    THRESHOLD_ERROR = 1000  # Error: file is too large

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check if file exceeds recommended size limits.

        Args:
            file_path: Path to file
            structure: Parsed structure (may be None for file-level check)
            content: File content

        Returns:
            List of detections (0 or 1 for file-level check)
        """
        detections = []

        try:
            path = Path(file_path)

            # Count lines
            line_count = content.count('\n') + 1

            # Get file size
            size_bytes = path.stat().st_size if path.exists() else len(content)

            # Human-readable size
            if size_bytes < 1024:
                size_str = f"{size_bytes}B"
            elif size_bytes < 1024**2:
                size_str = f"{size_bytes/1024:.1f}KB"
            else:
                size_str = f"{size_bytes/1024**2:.1f}MB"

            # Estimate token cost (rough heuristic: 1 char ≈ 0.75 tokens)
            est_tokens = int(size_bytes * 0.75)

            # Count functions and classes if structure available
            context_parts = [f"{line_count} lines", size_str]
            if structure:
                func_count = len(structure.get('functions', []))
                class_count = len(structure.get('classes', []))
                if func_count:
                    context_parts.append(f"{func_count} functions")
                if class_count:
                    context_parts.append(f"{class_count} classes")

            context = ", ".join(context_parts)

            # Determine severity and message
            if line_count > self.THRESHOLD_ERROR:
                severity = Severity.HIGH
                msg = f"{self.message} ({line_count:,} lines, {size_str})"
                suggestion = (
                    f"Split this {line_count:,}-line file into smaller, focused modules. "
                    f"Files >{self.THRESHOLD_ERROR} lines are hard to navigate and maintain. "
                    f"LLM cost: ~{est_tokens:,} tokens to load entire file. "
                    f"Use 'reveal {path.name}' (structure view) instead of reading full content."
                )
            elif line_count > self.THRESHOLD_WARN:
                severity = Severity.MEDIUM
                msg = f"{self.message} ({line_count:,} lines, consider splitting at {self.THRESHOLD_ERROR:,})"
                suggestion = (
                    f"This file is getting large. Consider splitting if it grows beyond {self.THRESHOLD_ERROR:,} lines. "
                    f"Use reveal's progressive disclosure: structure → outline → specific functions. "
                    f"Estimated LLM cost: ~{est_tokens:,} tokens."
                )
            else:
                return detections

            detections.append(Detection(
                file_path=file_path,
                line=1,
                rule_code=self.code,
                message=msg,
                column=1,
                suggestion=suggestion,
                context=context,
                severity=severity,
                category=self.category
            ))

        except Exception as e:
            logger.debug(f"M101 check failed on {file_path}: {e}")

        return detections
