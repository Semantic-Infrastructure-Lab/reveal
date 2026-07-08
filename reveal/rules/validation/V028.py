"""V028: help_data yaml must not carry a query-param block.

Adapter query params have exactly two documented homes, both guarded:
  1. the live get_schema()['query_params'] (source of truth, served by
     help://schemas/<x>), and
  2. the adapter's markdown guide param table (served by help://<x>,
     coherence-checked against the schema by V027, existence by V024).

A third home once existed — a `query_params`/`query_parameters` block in the
per-adapter help_data/*.yaml files — but it had **zero readers**: the only
query_params reader in the render path (_render_schema_query_params) is fed by
get_schema(), never by help_data. It rendered nowhere, used inconsistent key
naming, and drifted from the schema unnoticed — a trap for a maintainer who'd
edit it expecting it to be authoritative. It was removed (BACK-502/503).

This rule keeps it removed: it flags any help_data yaml that reintroduces a
top-level `query_params`/`query_parameters` key, pointing the fix back at the
two real surfaces. reveal:// self-check only (internal=True), same shape as
V024/V027.

See internal-docs/design/HELP_SYSTEM_ARCHITECTURE.md §5 for the full surface map.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...utils.path_utils import to_posix
from .utils import find_reveal_root

# The two key spellings the dead surface used across the yaml files.
_FORBIDDEN_KEYS = ('query_params', 'query_parameters')


class V028(BaseRule):
    """Flag help_data yaml files that carry a (dead) query-param block."""

    code = "V028"
    message = "help_data yaml carries a dead query-param block"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns: List[str] = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check that no help_data yaml reintroduces a query-param block."""
        if not file_path.startswith('reveal://'):
            return []

        try:
            import yaml
        except Exception:
            return []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return []
        # find_reveal_root() returns the package dir; help_data lives at
        # adapters/help_data directly under it.
        help_data_dir = reveal_root / 'adapters' / 'help_data'
        if not help_data_dir.exists():
            return []

        detections: List[Detection] = []
        for yaml_path in sorted(help_data_dir.glob('*.yaml')):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
            except Exception:
                # A malformed yaml is a different rule's problem, not ours.
                continue
            if not isinstance(data, dict):
                continue

            rel_path = to_posix(yaml_path.relative_to(reveal_root.parent))
            for key in _FORBIDDEN_KEYS:
                if key in data:
                    scheme = yaml_path.stem.replace('_uri', '')
                    detections.append(self.create_detection(
                        file_path=rel_path,
                        line=1,
                        message=(
                            f"{yaml_path.name} declares a top-level `{key}:` block — "
                            "query params are not served from help_data yaml (zero readers)"
                        ),
                        suggestion=(
                            f"Remove the `{key}:` block. Document {scheme}://'s params "
                            f"in get_schema()['query_params'] (source of truth) and its "
                            f"markdown guide (V027-checked); see "
                            f"internal-docs/design/HELP_SYSTEM_ARCHITECTURE.md §5"
                        ),
                        context=f"file={yaml_path.name}, key={key}",
                    ))

        return detections
