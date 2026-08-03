"""TypedDict definitions for reveal's Output Contract.

These types document the shape of data flowing through the system:
- Contract envelope: RevealResult, RevealMeta, WarningEntry
- AST element shapes: ASTElement, VarFlowEvent

RevealResult is the return type of get_structure() and ResultBuilder.create().
The envelope fields (contract_version, type, source, source_type) are always
present. meta is optional — only emitted for v1.1 contracts with parse metadata.

Adapter-specific data fields are spread at the top level via result.update(data),
so RevealResult is a minimum contract, not an exhaustive schema.
"""

from typing import Any, List, TypedDict


class WarningEntry(TypedDict, total=False):
    code: str
    message: str
    file: str
    fallback: str


class RevealMeta(TypedDict, total=False):
    parse_mode: str
    confidence: float
    warnings: List[WarningEntry]
    errors: List[WarningEntry]


class _RevealResultRequired(TypedDict):
    contract_version: str
    type: str
    source: str
    source_type: str


class RevealResult(_RevealResultRequired, total=False):
    """Output Contract envelope returned by all get_structure() implementations.

    The four required fields are always present. meta is present only for
    v1.1 results that include parse-quality metadata.

    Adapter-specific data fields (e.g. 'functions', 'imports', 'results') are
    spread into the dict by ResultBuilder.create() via result.update(data) —
    they are not captured here. Use a RevealResult subclass TypedDict for
    adapter-specific return shapes.
    """
    meta: RevealMeta
    error: str


# ---------------------------------------------------------------------------
# AST element TypedDicts
# These document the shapes produced at module boundaries in the ast adapter.
# ---------------------------------------------------------------------------

class ASTElement(TypedDict, total=False):
    """Element dict produced by analysis.create_element_dict().

    All fields are present for functions/methods. category='imports' and
    category='classes' omit complexity, depth, calls, called_by.
    """
    file: str
    category: str
    name: str
    line: int
    line_count: int
    signature: str
    decorators: List[str]
    # Functions/methods only:
    complexity: int
    depth: int
    calls: List[str]
    called_by: List[str]
    resolved_calls: List[Any]


class VarFlowEvent(TypedDict, total=False):
    """Single event in a varflow trace produced by VarFlowWalker.

    kind is one of: ENTRY, READ, WRITE, RETURN, CALL, ASSIGN.
    node is the tree-sitter Node — stripped by the renderer before output.
    text is only present on synthetic events (e.g. dict.update() expansions).
    """
    kind: str
    line: int
    node: Any
    text: str
