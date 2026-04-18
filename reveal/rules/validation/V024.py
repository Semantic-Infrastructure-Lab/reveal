"""V024: Adapter guide coverage.

Validates that every registered public URI adapter has a guide file in
docs/adapters/. Missing guides reduce discoverability and leave the adapter
undocumented for agents and users who rely on static docs.

Example violation:
    - Adapter: autossl://  (registered, public)
    - Missing: docs/adapters/AUTOSSL_ADAPTER_GUIDE.md

The check matches by prefix — any file starting with the adapter name (uppercase)
satisfies the rule, so both NGINX_GUIDE.md and NGINX_ADAPTER_GUIDE.md match nginx.

Exemptions:
    - help://  — the help system itself is the documentation layer
    - demo, test — internal adapters not in public registry
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V024(BaseRule):
    """Validate every public URI adapter has a guide doc in docs/adapters/."""

    code = "V024"
    message = "Registered adapter missing guide file in docs/adapters/"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = ['*']

    GUIDE_EXEMPT = {'demo', 'test', 'help'}

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        if not file_path.startswith('reveal://'):
            return []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return []

        schemes = self._get_public_schemes()
        if not schemes:
            return []

        guides = self._get_existing_guide_names(reveal_root)

        detections = []
        for scheme in sorted(schemes):
            if scheme in self.GUIDE_EXEMPT:
                continue
            if not self._has_guide(scheme, guides):
                detections.append(self.create_detection(
                    file_path=f"reveal/adapters/{scheme}",
                    line=1,
                    message=f"Adapter '{scheme}://' has no guide file in docs/adapters/",
                    suggestion=f"Create reveal/docs/adapters/{scheme.upper()}_ADAPTER_GUIDE.md",
                    context=(
                        f"No docs/adapters/ file starting with '{scheme.upper()}' found. "
                        f"All public adapters should have a guide."
                    )
                ))

        return detections

    def _get_public_schemes(self) -> Optional[List[str]]:
        try:
            from reveal.adapters.base import list_supported_schemes
            return list_supported_schemes()
        except Exception:
            return None

    def _get_existing_guide_names(self, reveal_root: Path) -> List[str]:
        guides_dir = reveal_root / 'docs' / 'adapters'
        if not guides_dir.exists():
            return []
        return [f.name.upper() for f in guides_dir.glob('*.md')]

    def _has_guide(self, scheme: str, guide_names: List[str]) -> bool:
        prefix = scheme.upper()
        return any(name.startswith(prefix) for name in guide_names)
