"""B003: @property with complex body detector.

Detects @property methods that are too complex. Properties should be simple
getters - if they have significant logic, they should be regular methods.

BACK-1011: ported to C# — a `get` accessor with a block body (not an
auto-property `{ get; set; }` or an expression-bodied `=> expr`) is the same
shape as a Python `@property`: syntactically a field access, semantically
allowed to hide arbitrary logic. Only the `get` accessor's own block is
measured (not `set`, which is a separate accessor_declaration sibling under
the same accessor_list). Kotlin/Swift not yet ported — see BACK-1011 note #7:
Kotlin's `getter` node is a *sibling* of `property_declaration` when the
getter is on its own line, but *nested inside* it for a same-line
`get() = expr` form, a real grammar-layout quirk that needs its own care
rather than reusing C#'s walk as-is.
"""

import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import TreeSitterParsingMixin
from ...core import node_children, _zero_arg

logger = logging.getLogger(__name__)


class B003(BaseRule, TreeSitterParsingMixin):
    """Detect @property methods with overly complex bodies."""

    code = "B003"
    message = "@property is too complex - properties should be simple getters"
    category = RulePrefix.B
    severity = Severity.MEDIUM
    file_patterns = ['.py', '.cs']
    version = "1.1.0"

    # Properties over this line count are flagged
    MAX_PROPERTY_LINES = 15

    _CS_LANGUAGE = 'csharp'

    thresholds = {"max_lines": MAX_PROPERTY_LINES}
    compliant_example = """\
@property
def status(self) -> str:
    return self._status  # Simple getter - good

# If logic is needed, use a regular method:
def compute_status(self) -> str:
    if self._error:
        return "error"
    return self._status"""

    # ── C# (BACK-1011) ───────────────────────────────────────────────────────

    def _check_csharp(self, file_path: str, content: str) -> List[Detection]:
        """Check C# `get` accessor blocks for line count, mirroring the
        Python @property check. Auto-properties (`{ get; set; }`, no block)
        and expression-bodied properties (`=> expr`, always one line) have
        nothing to measure and are skipped."""
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._CS_LANGUAGE)
        if root is None:
            return detections

        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'property_declaration':
                continue

            accessor_list = next(
                (c for c in node_children(node) if _zero_arg(c, 'kind') == 'accessor_list'), None
            )
            if accessor_list is None:
                continue  # expression-bodied property, e.g. `public string X => _x;`

            name = next(
                (self._ts_node_text(c, content.encode('utf-8'))
                 for c in node_children(node) if _zero_arg(c, 'kind') == 'identifier'),
                '?'
            )

            for accessor in node_children(accessor_list):
                if _zero_arg(accessor, 'kind') != 'accessor_declaration':
                    continue
                keyword, block = None, None
                for c in node_children(accessor):
                    k = _zero_arg(c, 'kind')
                    if k in ('get', 'set'):
                        keyword = k
                    elif k == 'block':
                        block = c
                if keyword != 'get' or block is None:
                    continue  # auto-property accessor (`get;`) or a `set`

                line = block.start_position().row + 1
                end_line = block.end_position().row + 1
                line_count = end_line - line + 1
                if line_count > self.MAX_PROPERTY_LINES:
                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=line,
                        message=f"@property '{name}' is {line_count} lines (max {self.MAX_PROPERTY_LINES})",
                        suggestion=f"Consider converting to a regular method: string Get{name}()",
                        context=f"get accessor with {line_count} lines - properties should be simple getters"
                    ))

        return detections

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for @property methods that are too long/complex.

        Properties should be simple attribute accessors. Complex logic belongs
        in regular methods.

        Args:
            file_path: Path to Python file
            structure: Parsed structure with functions and decorators
            content: File content

        Returns:
            List of detections
        """
        if file_path.endswith('.cs'):
            return self._check_csharp(file_path, content)

        detections: List[Detection] = []

        if not structure:
            return detections

        # Check all functions
        for func in structure.get('functions', []):
            decorators = func.get('decorators', [])
            name = func.get('name', '')
            line = func.get('line', 0)
            line_count = func.get('line_count', 0)

            # Check if it's a property (but not cached_property)
            # cached_property is OK to be complex since it's computed once and cached
            is_property = any(
                d == '@property' or
                (d.startswith('@property') and 'cached' not in d) or
                d.endswith('.getter')
                for d in decorators
            )

            # Exclude cached_property - it's OK to be complex
            is_cached = any(
                '@cached_property' in d
                for d in decorators
            )

            if is_cached:
                continue

            if not is_property:
                continue

            # Check if property is too complex (too many lines)
            if line_count > self.MAX_PROPERTY_LINES:
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=f"@property '{name}' is {line_count} lines (max {self.MAX_PROPERTY_LINES})",
                    suggestion=f"Consider converting to a regular method: def get_{name}(self)",
                    context=f"@property with {line_count} lines - properties should be simple getters"
                ))

        return detections
