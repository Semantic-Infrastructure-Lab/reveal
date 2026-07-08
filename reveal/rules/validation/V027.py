"""V027: Adapter guide / schema query-param coherence.

Validates that every URI adapter's live get_schema() query params are
documented in its *_ADAPTER_GUIDE.md, and that every param a guide's
"Parameter" table column names still exists in the schema.

Example violations:
    - Forward: git://'s get_schema() declares ?bucket=, but
      GIT_ADAPTER_GUIDE.md never mentions it — an undocumented live feature.
    - Reverse: STATS_ADAPTER_GUIDE.md's "Legacy Parameters" table lists
      `type`, but stats://'s schema has no such key — a stale/dead claim.

Method:
    - Forward direction: structural text match (?param=, ?param, `param`,
      param=, --param) — bare substring matching produces both false
      positives (common English words coincidentally appearing in prose)
      and false negatives (template-style schema keys like markdown://'s
      "field=value"), so template keys are excluded and matches require
      query/flag/code-span context. NOTE: this is deliberately a lenient
      text match, NOT the same tree-sitter table extraction the reverse
      direction uses — and that asymmetry is correct, not a shortcut.
      Forward asks "is this param documented *anywhere* in the guide?",
      and guides legitimately document params in prose, example URIs, and
      code blocks rather than only a "Parameter" table (claude:// documents
      all 16 of its params with none in a param-column table). Restricting
      forward to table-column extraction was measured against the live
      24-adapter corpus and produced 45 false positives vs. the text
      check's 0 misses — so the lenient direction stays lenient by design.
    - Reverse direction: real tree-sitter markdown parsing (pipe_table /
      pipe_table_header / pipe_table_row nodes), not backtick regex over
      the whole file — a naive regex scan conflates a table's "Parameter"
      column with adjacent "Values"/"Example" columns (e.g. enum values
      like `class`/`true`/`json` misread as param names). Reading the
      header row to find the actual "Parameter" column removes that
      ambiguity entirely. A table is a *strong structured claim* ("this is
      a real param"), so verifying it strictly against the schema is right;
      the asymmetry with the lenient forward check is intentional.
      Universal result-control params (limit, offset, sort) are excluded —
      they're handled by shared plumbing outside each adapter's own
      query_params schema, not per-adapter drift.
Scope:
    - reveal:// self-check only (internal=True), like V012/V013.
    - Adapter → guide file mapping is a simple naming convention
      (SCHEME_ADAPTER_GUIDE.md / SCHEME_GUIDE.md / SCHEMEGUIDE.md); an
      adapter with no matching guide file is skipped here because *guide
      existence* is V024's job (V024 flags any registered public adapter
      lacking a guide). V027 stays narrowly about param coherence within a
      guide that exists, so the two rules don't double-report the same gap.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...core.treesitter_compat import node_children
from ...utils.path_utils import to_posix
from .utils import find_reveal_root

# Universal result-control params handled by shared query-parsing plumbing,
# not declared in any individual adapter's get_schema()['query_params'] —
# legitimately absent from the schema even though guides document them.
_UNIVERSAL_RESULT_CONTROL = {'limit', 'offset', 'sort'}

# Adapter schemes with no adapter guide, skipped when pairing schemes to
# guides: help:// *is* the guide/help system itself (documented in-band, not
# via a *_GUIDE.md), and test/demo are test-fixture schemes. Guide *existence*
# for real adapters is V024's responsibility, not V027's — see module docstring.
_GUIDELESS_SCHEMES = {'help', 'test', 'demo'}

# Schema query-param keys that are generic filter-operator syntax templates
# (markdown://'s shared query DSL: "field=value", "field~=pattern", ...)
# rather than literal named params — documented once in a shared syntax
# guide, not repeated per-adapter, so they're not doc-coverage candidates.
_TEMPLATE_KEY_CHARS = set('=<>!~')


class V027(BaseRule):
    """Validate adapter guide docs match each adapter's live get_schema()."""

    code = "V027"
    message = "Adapter guide / schema query-param drift"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns: List[str] = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check adapter-guide coherence against live get_schema() output."""
        if not file_path.startswith('reveal://'):
            return []

        try:
            from tree_sitter_language_pack import get_parser
            from reveal.adapters.base import _ADAPTER_REGISTRY
        except Exception:
            return []

        # find_reveal_root() returns the reveal *package* dir (the one holding
        # analyzers/ and rules/), so the guides live directly under it at
        # docs/adapters — NOT reveal/docs/adapters. The earlier extra 'reveal'
        # segment pointed at a path that never exists, silently early-returning
        # here and making the whole rule a no-op (guarded now by the
        # test_live_registry_actually_ran regression test).
        reveal_root = find_reveal_root()
        if not reveal_root:
            return []
        guides_dir = reveal_root / 'docs' / 'adapters'
        if not guides_dir.exists():
            return []

        parser = get_parser('markdown')
        detections: List[Detection] = []

        schemes = sorted(set(_ADAPTER_REGISTRY.keys()) - _GUIDELESS_SCHEMES)
        for scheme in schemes:
            guide_path = self._guess_guide_file(scheme, guides_dir)
            if guide_path is None:
                # Guide existence is V024's job; V027 only checks coherence
                # within a guide that exists. Skip (don't double-report).
                continue

            try:
                schema = _ADAPTER_REGISTRY[scheme].get_schema()
            except Exception:
                continue
            query_params: Dict[str, Any] = schema.get('query_params') or {}

            guide_text = guide_path.read_text(encoding='utf-8')
            rel_path = to_posix(guide_path.relative_to(reveal_root.parent))

            detections.extend(self._check_forward(
                scheme, query_params, guide_text, rel_path
            ))
            detections.extend(self._check_reverse(
                scheme, query_params, guide_text, rel_path, parser
            ))

        return detections

    @staticmethod
    def _guess_guide_file(scheme: str, guides_dir: Path) -> Optional[Path]:
        """Map an adapter scheme to its guide file by naming convention."""
        for candidate in (
            f'{scheme.upper()}_ADAPTER_GUIDE.md',
            f'{scheme.upper()}_GUIDE.md',
            f'{scheme.upper()}GUIDE.md',
        ):
            path = guides_dir / candidate
            if path.exists():
                return path
        return None

    def _check_forward(
        self,
        scheme: str,
        query_params: Dict[str, Any],
        guide_text: str,
        rel_path: str,
    ) -> List[Detection]:
        """Flag schema query params never mentioned in the guide's text."""
        detections = []
        for param in query_params:
            if any(c in param for c in _TEMPLATE_KEY_CHARS) or param.startswith('!'):
                continue
            if self._documented_in_text(param, guide_text):
                continue
            detections.append(self.create_detection(
                file_path=rel_path,
                line=1,
                message=f"{scheme}://'s live ?{param}= query param is undocumented in its guide",
                suggestion=(
                    f"Add `{param}` to {rel_path}'s Query Parameters section "
                    f"(see `reveal help://schemas/{scheme}`)"
                ),
                context=f"scheme={scheme}, param={param}",
            ))
        return detections

    @staticmethod
    def _documented_in_text(param: str, text: str) -> bool:
        p = re.escape(param)
        patterns = [rf'\?{p}=', rf'\?{p}\b', rf'`{p}`', rf'{p}=', rf'--{p}\b']
        return any(re.search(pat, text) for pat in patterns)

    def _check_reverse(
        self,
        scheme: str,
        query_params: Dict[str, Any],
        guide_text: str,
        rel_path: str,
        parser: Any,
    ) -> List[Detection]:
        """Flag guide-documented params that no longer exist in the schema."""
        tree = parser.parse(guide_text)
        known_params = set(query_params.keys())

        detections = []
        for name, line in _iter_param_column_entries(tree.root_node(), guide_text):
            if name in _UNIVERSAL_RESULT_CONTROL or name in known_params:
                continue
            detections.append(self.create_detection(
                file_path=rel_path,
                line=line,
                message=(
                    f"{rel_path} documents `{name}` for {scheme}:// "
                    "but it's not in the live schema"
                ),
                suggestion=(
                    f"Remove the stale `{name}` row, or add it back to "
                    f"{scheme}://'s get_schema() if it's still a real feature"
                ),
                context=f"scheme={scheme}, param={name}",
            ))
        return detections


def _find_tables(node: Any) -> Iterator[Any]:
    """Yield every pipe_table node in the tree (not descending into one already found)."""
    if node.kind() == 'pipe_table':
        yield node
        return
    for child in node_children(node):
        yield from _find_tables(child)


def _iter_param_column_entries(root: Any, guide_text: str) -> Iterator[tuple]:
    """Yield (name, 1-indexed line) for every backtick-quoted name in a table's

    "Parameter"/"Param" column — identified via the header row, not by
    position, so an "Operator"/"Values"/"Example" column's own backtick
    content (enum values, etc.) is never mistaken for a param name.
    """
    content_bytes = guide_text.encode('utf-8')

    def cell_text(cell: Any) -> str:
        return content_bytes[cell.start_byte():cell.end_byte()].decode('utf-8').strip()

    for table in _find_tables(root):
        header = next(
            (c for c in node_children(table) if c.kind() == 'pipe_table_header'),
            None,
        )
        if header is None:
            continue
        headers = [cell_text(c) for c in node_children(header) if c.kind() == 'pipe_table_cell']
        param_col = next(
            (i for i, h in enumerate(headers) if h.lower() in ('parameter', 'param')),
            None,
        )
        if param_col is None:
            continue

        for row in node_children(table):
            if row.kind() != 'pipe_table_row':
                continue
            cells = [c for c in node_children(row) if c.kind() == 'pipe_table_cell']
            if param_col >= len(cells):
                continue
            line = row.start_position().row + 1
            for name in re.findall(r'`([a-zA-Z][a-zA-Z0-9_-]*)`', cell_text(cells[param_col])):
                yield name, line
