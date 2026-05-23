"""V025: Adapter relationship map coverage.

Validates that every registered public URI adapter appears in at least one
cluster in help://relationships. The relationship map is hand-maintained and
silently goes stale when new adapters are added without updating the map.

This rule makes `reveal:// --check` catch that drift instead of reporting clean.

Example violation:
    - Adapter: patches://  (registered, public)
    - Missing from: help://relationships cluster list

Exemptions:
    - demo, test — internal adapters excluded from public listings
    - help — the help adapter documents the relationship map itself
"""

from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V025(BaseRule):
    """Validate every public adapter appears in help://relationships clusters."""

    code = "V025"
    message = "Registered adapter missing from help://relationships cluster map"
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = ['*']

    RELATIONSHIP_EXEMPT = {'demo', 'test', 'help'}

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

        mapped = self._get_mapped_adapters()
        if mapped is None:
            return []

        detections = []
        for scheme in sorted(schemes):
            if scheme in self.RELATIONSHIP_EXEMPT:
                continue
            if scheme not in mapped:
                detections.append(self.create_detection(
                    file_path="reveal/adapters/help.py",
                    line=1,
                    message=f"Adapter '{scheme}://' not in any help://relationships cluster",
                    suggestion=(
                        f"Add '{scheme}' to a cluster in "
                        f"HelpAdapter._get_adapter_relationships() in reveal/adapters/help.py"
                    ),
                    context=(
                        f"'{scheme}' is registered in _ADAPTER_REGISTRY but absent from "
                        f"help://relationships. Agents relying on the relationship map will "
                        f"not discover it. Add it to the appropriate cluster and add relevant "
                        f"adapter pairs."
                    )
                ))

        return detections

    def _get_public_schemes(self) -> Optional[List[str]]:
        try:
            from reveal.adapters.base import list_supported_schemes
            return list_supported_schemes()
        except Exception:
            return None

    def _get_mapped_adapters(self) -> Optional[set]:
        try:
            from reveal.adapters.help import HelpAdapter
            adapter = HelpAdapter('relationships')
            data = adapter.get_element('relationships')
            clusters = data.get('clusters', [])
            return {a for cluster in clusters for a in cluster.get('adapters', [])}
        except Exception:
            return None
