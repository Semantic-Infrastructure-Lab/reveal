"""B003: @property with complex body detector.

Detects @property methods that are too complex. Properties should be simple
getters - if they have significant logic, they should be regular methods.

BACK-1011: ported to C# — a `get` accessor with a block body (not an
auto-property `{ get; set; }` or an expression-bodied `=> expr`) is the same
shape as a Python `@property`: syntactically a field access, semantically
allowed to hide arbitrary logic. Only the `get` accessor's own block is
measured (not `set`, which is a separate accessor_declaration sibling under
the same accessor_list).

Kotlin: real grammar-layout quirk confirmed via direct AST inspection (BACK-
1011 note #7) — a `getter` node is a *sibling* of `property_declaration`
under `class_body` when the getter is on its own line (`val bar: String\n
get() { ... }`), but *nested inside* it for a same-line `get() = expr`
form. Both shapes are handled: the sibling case walks backward to the
nearest preceding `property_declaration` for the name (nodes aren't
identity/equality-comparable across separate tree-sitter accesses, so
siblings are matched by `start_byte`, not `is`/`==`/`.index()`). Only a
block-bodied getter (`get() { ... }`) is measured — `get() = expr`
(expression form) has nothing to measure, same exclusion as C#'s `=> expr`.

Swift: `computed_property` is always nested inside `property_declaration`
(no Kotlin-style sibling quirk). Two shapes measured: an explicit `get { }`
block (`computed_getter` node) and the implicit-getter shorthand — a
read-only computed property with no `get`/`set` keyword at all
(`var x: T { <body> }`) — whose `computed_property` node IS the getter
body. `willSet`/`didSet` observers live under a different node kind
(`willset_didset_block`, not `computed_property`) and are correctly never
matched — they're stored-property write hooks, not a getter. A
`computed_setter`-only property (no getter) is invalid Swift but handled
defensively by skipping it rather than crashing.
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
    file_patterns = ['.py', '.cs', '.kt', '.kts', '.swift']
    version = "1.2.0"

    # Properties over this line count are flagged
    MAX_PROPERTY_LINES = 8  # BACK-1063: was 15, drifted from RuleDefaults.MAX_PROPERTY_LINES

    _CS_LANGUAGE = 'csharp'
    _KOTLIN_LANGUAGE = 'kotlin'
    _SWIFT_LANGUAGE = 'swift'

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

                line = _zero_arg(block, 'start_position').row + 1
                end_line = _zero_arg(block, 'end_position').row + 1
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

    # ── Kotlin (BACK-1011) ───────────────────────────────────────────────────

    def _check_kotlin(self, file_path: str, content: str) -> List[Detection]:
        """Check Kotlin `getter` blocks for line count. Handles both the
        sibling-of-property_declaration and nested-in-property_declaration
        grammar shapes — see module docstring."""
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._KOTLIN_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')

        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'getter':
                continue

            function_body = next(
                (c for c in node_children(node) if _zero_arg(c, 'kind') == 'function_body'), None
            )
            if function_body is None:
                continue

            body_children = node_children(function_body)
            if not body_children or _zero_arg(body_children[0], 'kind') != '{':
                continue  # expression-bodied `get() = expr` — nothing to measure

            name = self._kotlin_property_name(node, content_bytes)
            line = _zero_arg(function_body, 'start_position').row + 1
            end_line = _zero_arg(function_body, 'end_position').row + 1
            line_count = end_line - line + 1
            if line_count > self.MAX_PROPERTY_LINES:
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=f"@property '{name}' is {line_count} lines (max {self.MAX_PROPERTY_LINES})",
                    suggestion=f"Consider converting to a regular method: fun get{name[:1].upper()}{name[1:]}()",
                    context=f"getter with {line_count} lines - properties should be simple getters"
                ))

        return detections

    def _kotlin_property_name(self, getter_node, content_bytes: bytes) -> str:
        """Resolve a `getter` node's owning property name, handling both the
        nested (same-line `get() = expr`) and sibling (own-line `get() {}`)
        grammar shapes. Nodes from separate tree-sitter accesses aren't
        identity/equality-comparable, so the sibling case matches by
        `start_byte` rather than `is`/`==`/`list.index()`."""
        parent = _zero_arg(getter_node, 'parent')
        if parent is None:
            return '?'
        if _zero_arg(parent, 'kind') == 'property_declaration':
            return self._kotlin_extract_name(parent, content_bytes)

        siblings = node_children(parent)
        getter_start = _zero_arg(getter_node, 'start_byte')
        idx = next(
            (i for i, s in enumerate(siblings) if _zero_arg(s, 'start_byte') == getter_start), None
        )
        if idx is None:
            return '?'
        for sib in reversed(siblings[:idx]):
            if _zero_arg(sib, 'kind') == 'property_declaration':
                return self._kotlin_extract_name(sib, content_bytes)
        return '?'

    def _kotlin_extract_name(self, property_decl_node, content_bytes: bytes) -> str:
        for c in node_children(property_decl_node):
            if _zero_arg(c, 'kind') == 'variable_declaration':
                for gc in node_children(c):
                    if _zero_arg(gc, 'kind') == 'simple_identifier':
                        return self._ts_node_text(gc, content_bytes)
        return '?'

    # ── Swift (BACK-1011) ────────────────────────────────────────────────────

    def _check_swift(self, file_path: str, content: str) -> List[Detection]:
        """Check Swift computed-property getters for line count. Measures an
        explicit `get { }` block or, for the implicit-getter shorthand
        (`var x: T { <body> }`, no `get`/`set` keyword), the whole
        `computed_property` body. `willSet`/`didSet` observers (a different
        node kind entirely) and set-only properties are never matched."""
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._SWIFT_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')

        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'property_declaration':
                continue

            computed_property = next(
                (c for c in node_children(node) if _zero_arg(c, 'kind') == 'computed_property'), None
            )
            if computed_property is None:
                continue  # stored property, or a willSet/didSet observer block

            cp_children = node_children(computed_property)
            computed_getter = next(
                (c for c in cp_children if _zero_arg(c, 'kind') == 'computed_getter'), None
            )
            has_setter = any(_zero_arg(c, 'kind') == 'computed_setter' for c in cp_children)

            if computed_getter is not None:
                target = computed_getter
            elif not has_setter:
                target = computed_property  # implicit-getter shorthand
            else:
                continue  # set-only, no getter to measure (invalid Swift, but be defensive)

            name = self._swift_property_name(node, content_bytes)
            line = _zero_arg(target, 'start_position').row + 1
            end_line = _zero_arg(target, 'end_position').row + 1
            line_count = end_line - line + 1
            if line_count > self.MAX_PROPERTY_LINES:
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=f"@property '{name}' is {line_count} lines (max {self.MAX_PROPERTY_LINES})",
                    suggestion=f"Consider converting to a regular method: func get{name[:1].upper()}{name[1:]}()",
                    context=f"computed property getter with {line_count} lines - properties should be simple getters"
                ))

        return detections

    def _swift_property_name(self, property_decl_node, content_bytes: bytes) -> str:
        for c in node_children(property_decl_node):
            if _zero_arg(c, 'kind') == 'pattern':
                for gc in node_children(c):
                    if _zero_arg(gc, 'kind') == 'simple_identifier':
                        return self._ts_node_text(gc, content_bytes)
        return '?'

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
        if file_path.endswith(('.kt', '.kts')):
            return self._check_kotlin(file_path, content)
        if file_path.endswith('.swift'):
            return self._check_swift(file_path, content)

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
