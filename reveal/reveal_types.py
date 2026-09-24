"""TypedDict definitions for reveal's Output Contract.

These types document the shape of data flowing through the system:
- Contract envelope: RevealResult, RevealMeta, WarningEntry
- AST element shapes: StructureItem (analyzer output), ASTElement (adapter
  record built from it), VarFlowEvent

RevealResult is the return type of get_structure() and ResultBuilder.create().
The envelope fields (contract_version, type, source, source_type) are always
present. meta is optional — only emitted for v1.1 contracts with parse metadata.

Adapter-specific data fields are spread at the top level via result.update(data),
so RevealResult is a minimum contract, not an exhaustive schema.
"""

from typing import Any, List, TypedDict


# Current Output Contract version emitted by adapters/analyzers that opt into
# v1.1 fields (meta/parse_mode/confidence/...). ResultBuilder.create()'s own
# `contract_version` default stays '1.0' (the baseline contract, still valid
# for callers that don't pass v1.1 metadata) — this constant is for the ~150
# call sites that were duplicating the '1.1' string literal (BACK-910).
CONTRACT_VERSION = '1.1'


class WarningEntry(TypedDict, total=False):
    code: str
    # ast://, hotspots, stats, and the Kotlin/OpenXML analyzers key the warning's
    # kind as 'type' rather than 'code' (e.g. 'unknown_sort_field'); both occur.
    type: str
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
    # Set by an analyzer whose parser recovered from malformed input (BACK-1084/
    # BACK-1404); `check` reads it as "results may be incomplete", not clean.
    _has_errors: bool


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
    bases: List[str]
    # Optional flags propagated from the analyzer (absent unless true):
    is_abstract: bool
    is_test_callback: bool
    accessor: str
    trait_impl: bool
    # Functions/methods only:
    complexity: int
    depth: int
    calls: List[str]
    called_by: List[str]
    resolved_calls: List[Any]


class StructureItem(TypedDict, total=False):
    """One entry of an analyzer's get_structure() lists (functions, classes,
    imports, ...): the input create_element_dict() turns into an ASTElement.

    Line-range keys are `line` (start) and `line_end` (inclusive end); the
    extract_element() records use `line_start`/`line_end`. `end_line` is not
    a key of either record -- it only names local variables and the parsed
    `:N-M` element syntax (BACK-1292).
    """
    name: str
    line: int
    line_start: int
    line_end: int
    line_count: int
    code_line_count: int
    signature: str
    decorators: List[str]
    bases: List[str]
    is_abstract: bool
    is_test_callback: bool
    accessor: str
    trait_impl: bool
    complexity: int
    depth: int
    calls: List[str]
    called_by: List[str]
    content: str  # imports carry their text here instead of `name`
    visibility: str  # Zig `pub`
    members: List[str]  # Zig struct/enum/union member names
    type: str  # PowerShell class entries


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
