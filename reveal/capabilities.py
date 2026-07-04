"""Language capability registry (BACK-444).

Reveal supports 40+ languages via explicit analyzers registered in
``reveal/registry.py``, but not every language has the same *trustworthiness*
for every feature: ``--varflow`` is ground-truth-verified for the 9
conformance-matrix languages, smoke-tested (non-crash/non-empty only) for
another 10, and structure-only (no nav-flag surface at all) for the tier C
languages. Before this module, that knowledge lived only in analyzer source
comments, test files, and design docs — no single machine-readable place an
agent or user could query "is --varflow safe to trust for Rust?".

This module is that place. It does not re-derive facts — every field here is
grounded in a specific test file or design-doc finding, cited in each entry's
``known_limitations`` or in the per-tier comments below. See
``internal-docs/design/MULTI_LANGUAGE_ARCHITECTURE_2026-07-03.md`` (Issue G)
for the full narrative and ``internal-docs/BACKLOG.md`` (BACK-444) for the
originating request.

Conformance tiers (``conformance_level``), from strongest to weakest evidence:

* ``tier1-verified``   — one of the 9 languages in
  ``tests/test_conformance_matrix.py``: a real fixture + hand-written
  ``expected.yaml`` ground truth checked against every nav flag.
* ``smoke-tested``      — one of the 10 languages in
  ``tests/test_smoke_tier.py``: asserts every nav flag produces non-empty,
  non-crashing, structurally sane output, backed by at least one real-corpus
  dogfood pass (see ``internal-docs/planning/LANGUAGE_DOGFOOD_CORPUS_2026-07-02.md``).
  Not full ground truth — absence of a *known* bug is not proof of none.
* ``structure-only``    — one of the 8 "tier C" languages in
  ``tests/test_tier_c.py``: confirmed via ``--language-info`` to expose only
  "File structure" (no nav-flag surface at all), so there is nothing for
  ``--varflow``/``--exits``/etc. to be trustworthy *about*.
* ``untested``          — registered and reachable, but has no conformance
  matrix entry, no smoke-tier entry, and no tier C corpus mapping. Mostly
  non-code data/config/document formats where "varflow" has no meaning, plus
  a couple of registrations found to be dead code during this audit (see
  their ``known_limitations``).

``varflow`` mirrors the same four levels (``"verified"``, ``"smoke-tested"``,
``"not-applicable"``, ``"untested"``) rather than a bare bool, since "is
--varflow trustworthy" genuinely has more than two answers for this codebase.
``imports_unused`` stays a plain ``Optional[bool]`` as specified in BACK-444
(``True`` only where a bespoke or generic extractor's ``extract_symbols`` is
implemented and evidence shows results are relied upon; ``False`` where an
extractor exists but is known-unreliable and always suppresses "unused"
findings via ``skip_unused``; ``None`` where no import extractor is
registered for the language at all).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .registry import get_analyzer_mapping

# --- varflow trust levels --------------------------------------------------

VARFLOW_VERIFIED = "verified"
VARFLOW_SMOKE_TESTED = "smoke-tested"
VARFLOW_NOT_APPLICABLE = "not-applicable"
VARFLOW_UNTESTED = "untested"

_VARFLOW_LEVELS = frozenset({
    VARFLOW_VERIFIED, VARFLOW_SMOKE_TESTED, VARFLOW_NOT_APPLICABLE, VARFLOW_UNTESTED,
})

# --- conformance levels -----------------------------------------------------

CONFORMANCE_TIER1_VERIFIED = "tier1-verified"
CONFORMANCE_SMOKE_TESTED = "smoke-tested"
CONFORMANCE_STRUCTURE_ONLY = "structure-only"
CONFORMANCE_UNTESTED = "untested"

_CONFORMANCE_LEVELS = frozenset({
    CONFORMANCE_TIER1_VERIFIED, CONFORMANCE_SMOKE_TESTED,
    CONFORMANCE_STRUCTURE_ONLY, CONFORMANCE_UNTESTED,
})


@dataclass(frozen=True)
class LanguageCapability:
    """A machine-readable profile of what reveal actually knows to be true
    about one language's analysis quality.

    Fields match the shape specified in BACK-444 (internal-docs/BACKLOG.md).
    """

    language: str
    analyzer: str
    function_body_shape: str
    varflow: str  # one of the VARFLOW_* levels above
    imports_unused: Optional[bool]
    import_resolution: str
    conformance_level: str  # one of the CONFORMANCE_* levels above
    known_limitations: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.varflow not in _VARFLOW_LEVELS:
            raise ValueError(
                f"{self.language}: varflow={self.varflow!r} not one of {sorted(_VARFLOW_LEVELS)}"
            )
        if self.conformance_level not in _CONFORMANCE_LEVELS:
            raise ValueError(
                f"{self.language}: conformance_level={self.conformance_level!r} "
                f"not one of {sorted(_CONFORMANCE_LEVELS)}"
            )


# ---------------------------------------------------------------------------
# Tier 1 — deep conformance matrix (tests/test_conformance_matrix.py, 9
# languages, fixture + expected.yaml ground truth for every nav flag).
# ---------------------------------------------------------------------------

_TIER1: Dict[str, LanguageCapability] = {
    "PythonAnalyzer": LanguageCapability(
        language="python",
        analyzer="reveal.analyzers.python.PythonAnalyzer",
        function_body_shape=(
            "Standard block-nested statements — the reference C/Python shape "
            "the rest of the taxonomy was grown against."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=True,
        import_resolution=(
            "Bespoke extractor (imports/python.py) with full resolve_import "
            "to sibling/package files and extract_symbols for accurate "
            "unused-import detection."
        ),
        conformance_level=CONFORMANCE_TIER1_VERIFIED,
        known_limitations=[
            "No dedicated real-corpus dogfood clone exists for Python itself "
            "(internal-docs BACK-431 Issue G: deep-9 feature-breadth pass "
            "covered 18 of 19 target languages, skipping Python) — its "
            "verified status rests on the conformance matrix + smoke "
            "fixtures only, not an additional real-repo pass like every "
            "other tier1/A/B language got.",
        ],
    ),
    "RustAnalyzer": LanguageCapability(
        language="rust",
        analyzer="reveal.analyzers.rust.RustAnalyzer",
        function_body_shape=(
            "Expression-oriented: a block's tail expression (no trailing "
            "semicolon) is the function's implicit return value; loop/match "
            "conditions are expressions too (test_rust_outline_recognizes_"
            "expression_oriented_control_flow, test_conformance_matrix.py)."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=True,
        import_resolution=(
            "Bespoke extractor (imports/rust.py) resolves use-paths; pub use "
            "re-exports are correctly marked skip_unused so they are never "
            "falsely flagged (fixed BACK-431 Issue G, 15 false positives in "
            "one real Meilisearch file before the fix)."
        ),
        conformance_level=CONFORMANCE_TIER1_VERIFIED,
        known_limitations=[
            "BACK-428 (open, documented in tests/fixtures/conformance/"
            "expected.yaml): --exits/--returns only recognize explicit "
            "`return`; the `?` postfix operator and bare tail-expression "
            "implicit returns are invisible to both flags.",
            "BACK-431 Issue G (documented-not-fixed): a macro invocation's "
            "body (`token_tree`, e.g. lazy_static!{...}) has no internal AST "
            "structure to tree-sitter, so every identifier inside one reads "
            "as an independent variable to --varflow/--deps. Left open: "
            "blanket-excluding token_tree would also hide genuine variable "
            "references inside common macros like println!.",
        ],
    ),
    "GoAnalyzer": LanguageCapability(
        language="go",
        analyzer="reveal.analyzers.go.GoAnalyzer",
        function_body_shape="Standard block-nested, C-shaped.",
        varflow=VARFLOW_VERIFIED,
        imports_unused=True,
        import_resolution=(
            "Bespoke extractor (imports/go.py) resolves within-module import "
            "paths; fixed BACK-431 Issue G to derive the local package name "
            "from the segment before a semantic-import-versioning /vN "
            "suffix (e.g. k8s.io/klog/v2 -> klog, not v2)."
        ),
        conformance_level=CONFORMANCE_TIER1_VERIFIED,
        known_limitations=[
            "BACK-451 (open): named `Class.method` extraction syntax fails "
            "for Go — methods are free functions with a receiver parameter, "
            "not nested under a type body, so literal Class.method syntax "
            "may never apply; `:LINE-RANGE` is the working workaround.",
        ],
    ),
    "CAnalyzer": LanguageCapability(
        language="c",
        analyzer="reveal.analyzers.c.CAnalyzer",
        function_body_shape="Standard block-nested, the reference C shape.",
        varflow=VARFLOW_VERIFIED,
        imports_unused=False,
        import_resolution=(
            "Generic per-language table extractor (imports/generic.py); "
            "file-level #include dependency edges resolve for local headers, "
            "angle-bracket system includes intentionally unresolved. "
            "Unused-import detection is not attempted — every import is "
            "flagged skip_unused since textual #include lacks reliable "
            "symbol-usage semantics."
        ),
        conformance_level=CONFORMANCE_TIER1_VERIFIED,
        known_limitations=[],
    ),
    "CppAnalyzer": LanguageCapability(
        language="cpp",
        analyzer="reveal.analyzers.cpp.CppAnalyzer",
        function_body_shape=(
            "Standard block-nested, C++-shaped; for_range_loop (range-based "
            "for) has its own declarator/right field shape distinct from "
            "every other FOR-family node."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=False,
        import_resolution=(
            "Same generic textual #include extractor as C: listing and "
            "local-header dependency edges only, unused-detection not "
            "claimed (skip_unused always set)."
        ),
        conformance_level=CONFORMANCE_TIER1_VERIFIED,
        known_limitations=[
            "BACK-450 (open): for_range_loop has no --varflow dispatch case "
            "— the loop variable/iterable aren't classified WRITE/READ, "
            "though --outline/--ifmap/--loopmap/--exits already see the "
            "loop correctly.",
            "BACK-451 (open): named `Class.method` extraction fails for "
            "C++ (method-under-class nesting doesn't resolve); "
            "`:LINE-RANGE` is the working workaround.",
            "BACK-421 Part 2 (open): Class::method qualifiers are stripped "
            "during name extraction, losing class association for "
            "out-of-line method definitions.",
            "BACK-421 Part 3 (open, pinned in expected.yaml L20): "
            "--exits/--returns/--ifmap/--mutations miss macro-hidden early "
            "returns (e.g. CHECK_OR_RETURN(...)) since tree-sitter sees only "
            "the unexpanded macro call.",
        ],
    ),
    "JavaAnalyzer": LanguageCapability(
        language="java",
        analyzer="reveal.analyzers.java.JavaAnalyzer",
        function_body_shape=(
            "Standard block-nested; annotations, field_access, and "
            "method_invocation all needed explicit member-access/"
            "compile-time-only exclusions (fixed BACK-431 Issue G) to avoid "
            "misreading class/field/method names as variable reads."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=False,
        import_resolution=(
            "Generic textual extractor (imports/generic.py); listing only, "
            "unused-detection not claimed."
        ),
        conformance_level=CONFORMANCE_TIER1_VERIFIED,
        known_limitations=[],
    ),
    "CSharpAnalyzer": LanguageCapability(
        language="csharp",
        analyzer="reveal.analyzers.csharp.CSharpAnalyzer",
        function_body_shape="Standard block-nested.",
        varflow=VARFLOW_VERIFIED,
        imports_unused=False,
        import_resolution=(
            "Generic textual extractor (imports/generic.py); listing only, "
            "unused-detection not claimed."
        ),
        conformance_level=CONFORMANCE_TIER1_VERIFIED,
        known_limitations=[],
    ),
    "JavaScriptAnalyzer": LanguageCapability(
        language="javascript",
        analyzer="reveal.analyzers.javascript.JavaScriptAnalyzer",
        function_body_shape=(
            "Standard block-nested; arrow functions (const f = () => {}) "
            "are extracted via the shared TreeSitterAnalyzer base (promoted "
            "from TypeScript-only during BACK-431 Issue G), so nav-flag "
            "lookup-by-name and plain element display both see them."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=True,
        import_resolution=(
            "Bespoke extractor (imports/javascript.py), shared with "
            "TypeScript/TSX for .js/.jsx/.ts/.tsx/.mjs/.cjs."
        ),
        conformance_level=CONFORMANCE_TIER1_VERIFIED,
        known_limitations=[],
    ),
    "TypeScriptAnalyzer": LanguageCapability(
        language="typescript",
        analyzer="reveal.analyzers.typescript.TypeScriptAnalyzer",
        function_body_shape=(
            "Same as JavaScript plus type annotations/interfaces; arrow-"
            "function extraction now lives on the shared base, not a "
            "TypeScript-only override."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=True,
        import_resolution="Same bespoke extractor as JavaScript.",
        conformance_level=CONFORMANCE_TIER1_VERIFIED,
        known_limitations=[],
    ),
}

# ---------------------------------------------------------------------------
# Tier A/B — smoke tier (tests/test_smoke_tier.py): every nav flag asserted
# non-crashing/non-empty, backed by at least one real-corpus dogfood pass,
# but with no expected.yaml ground truth.
# ---------------------------------------------------------------------------

_SMOKE: Dict[str, LanguageCapability] = {
    "KotlinAnalyzer": LanguageCapability(
        language="kotlin",
        analyzer="reveal.analyzers.kotlin.KotlinAnalyzer",
        function_body_shape=(
            "Expression-oriented if/when (when_expression/when_entry, "
            "fully fieldless); property_declaration exposes no fields at "
            "all, unlike Swift's node of the same name."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=None,
        import_resolution="No import extractor registered for .kt/.kts.",
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "navigation_expression member-access exclusion and "
            "function_declaration's fieldless self-name detection were "
            "found+fixed via real-corpus (tivi) dogfooding — no known open "
            "gap, but never had full expected.yaml ground truth.",
            "imports://?unused is unsupported (no extractor) — the text "
            "renderer previously showed a false-confidence checkmark here "
            "until BACK-431 Issue G's scanned_files metadata fix.",
        ],
    ),
    "SwiftAnalyzer": LanguageCapability(
        language="swift",
        analyzer="reveal.analyzers.swift.SwiftAnalyzer",
        function_body_shape=(
            "Identifiers parse as simple_identifier (unique among reveal's "
            "languages); switch_entry case arms and the leading-dot "
            "implicit-member shorthand (.someCase) are fieldless."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=None,
        import_resolution="No import extractor registered.",
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "Total --varflow blindness for every Swift variable (the "
            "simple_identifier kind was unchecked at all 3 read/write/"
            "declared sites) was found+fixed via the smoke fixture — the "
            "exact BACK-427-class failure this tier exists to catch.",
            "External argument labels and leading-dot implicit members were "
            "found+fixed via real-corpus (ios-oss) dogfooding.",
        ],
    ),
    "RubyAnalyzer": LanguageCapability(
        language="ruby",
        analyzer="reveal.analyzers.ruby.RubyAnalyzer",
        function_body_shape=(
            "Paren-less method defs (def human? ... end, no parens at all); "
            "implicit last-expression return, statement modifiers "
            "(return x if y)."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=False,
        import_resolution=(
            "Generic extractor (imports/generic.py) with call-style "
            "require/require_relative support; unused-detection not "
            "claimed (skip_unused always set)."
        ),
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "Signature-display duplication (human?human?) for paren-less "
            "defs found+fixed via Discourse real-corpus dogfooding — a "
            "shared display-layer fallback bug, most visible in Ruby.",
            "`call` (receiver.method(args)) member-access exclusion and "
            "--calls callee extraction both needed Ruby-specific branches, "
            "found+fixed via the same pass.",
        ],
    ),
    "PhpAnalyzer": LanguageCapability(
        language="php",
        analyzer="reveal.analyzers.php.PhpAnalyzer",
        function_body_shape=(
            "elseif_clause sits in _GATE_NODE_TYPES but was historically "
            "absent from SCOPE_NODES/KEYWORD_LABEL (BACK-431 Issue G flagged "
            "the drift); case_statement/default_statement are the real "
            "switch-arm kinds (the switch_case/switch_default placeholders "
            "previously in the taxonomy matched no real PHP parse)."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=False,
        import_resolution=(
            "Generic extractor (imports/generic.py) with require/include "
            "statement + call-style support; unused-detection not claimed."
        ),
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "case_statement/default_statement switch arms were invisible to "
            "--ifmap until fixed via real WordPress dogfooding.",
        ],
    ),
    "ScalaAnalyzer": LanguageCapability(
        language="scala",
        analyzer="reveal.analyzers.scala.ScalaAnalyzer",
        function_body_shape=(
            "val_definition/var_definition declarations; enumerator "
            "(for-comprehension bindings) is one fieldless node kind "
            "covering 3 shapes (generator/value/guard); throw parses as "
            "throw_expression, not throw_statement."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=None,
        import_resolution="No import extractor registered.",
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "val/var_definition WRITE-as-READ mislabeling and "
            "throw_expression invisibility to --exits/--returns were "
            "found+fixed via smoke + real-corpus (gitbucket) dogfooding.",
            "Named call arguments (f(x = value)) parse as "
            "assignment_expression, structurally identical to a real "
            "reassignment — fixed with an arguments-node-aware branch.",
        ],
    ),
    "DartAnalyzer": LanguageCapability(
        language="dart",
        analyzer="reveal.analyzers.dart.DartAnalyzer",
        function_body_shape=(
            "UNIQUE among reveal's languages: a function is TWO SIBLING "
            "nodes (function_signature + function_body), not one nested "
            "node; class methods wrap the signature in an extra "
            "method_signature layer. Fixed via TreeSitterAnalyzer."
            "_function_end_node() pairing the siblings, used by both "
            "--outline and file_handler's nav-flag range resolution."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=None,
        import_resolution="No import extractor registered.",
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "Was the worst blindness of tier B: every Dart function's body "
            "was silently truncated to its one-line signature until the "
            "sibling-pairing fix above landed.",
            "obj.method(x) has no member-access wrapper node — bare "
            "identifier + flat sibling selector nodes — needed dedicated "
            "reconstruction in both nav_varflow.py and nav_calls.py, found "
            "via AppFlowy real-corpus dogfooding.",
            "Class.method named extraction silently failed for Dart "
            "entirely until function_signature was added to "
            "CHILD_NODE_TYPES.",
        ],
    ),
    "LuaAnalyzer": LanguageCapability(
        language="lua",
        analyzer="reveal.analyzers.lua.LuaAnalyzer",
        function_body_shape=(
            "assignment_statement and table-constructor field nodes are "
            "fully fieldless (positional variable_list/expression_list "
            "children); function table.name(...) declarations have a "
            "dot_index_expression name node distinct from every "
            "plain-identifier case."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=None,
        import_resolution="No import extractor registered.",
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "VarFlowWalker (used directly by --varflow) lacked "
            "member-access exclusion generally — found via Kong real-corpus "
            "dogfooding, fixed generally for every language including "
            "Python.",
            "function table.name(...) had no name at all before the "
            "dotted-segment fallback fix (a common Kong-style public-API "
            "pattern).",
        ],
    ),
    "ZigAnalyzer": LanguageCapability(
        language="zig",
        analyzer="reveal.analyzers.zig.ZigAnalyzer",
        function_body_shape=(
            "Entirely fieldless grammar — no child_by_field_name support "
            "anywhere; Decl/FnProto (not function_definition) needs its own "
            "extractor; SuffixExpr packs an entire dotted-call chain into "
            "one node's children rather than nesting."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=None,
        import_resolution="No import extractor registered.",
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "Was total blindness for every single-function nav flag "
            "('could not find function or method') until ZigAnalyzer."
            "_get_node_name() + 'Decl' in FUNCTION_NODE_TYPES were added.",
            "SwitchExpr/SwitchProng needed adding to SWITCH_NODES/"
            "CASE_NODES, found via Ghostty's pervasive switch usage.",
            "_collect_identifier_names and --calls were both fully blind "
            "to Zig's all-caps IDENTIFIER kind and SuffixExpr call chains "
            "until BACK-431 Issue G's feature-breadth pass fixed both.",
        ],
    ),
    "GDScriptAnalyzer": LanguageCapability(
        language="gdscript",
        analyzer="reveal.analyzers.gdscript.GDScriptAnalyzer",
        function_body_shape=(
            "Declared identifiers are a name-kind leaf, disjoint from the "
            "identifier kind used at read sites; dotted method calls "
            "(x.size()) fold into the same attribute node Python uses for "
            "plain attribute access, with attribute_call vs bare identifier "
            "segments distinguishing real calls from property reads."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=None,
        import_resolution="No import extractor registered.",
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "var x = f() was invisible to --varflow entirely until the "
            "name-kind leaf case was added (found via the smoke fixture).",
            "--calls was partially blind to attribute_call dotted calls "
            "until fixed via godot-demo-projects real-corpus dogfooding; "
            "--deps was already clean.",
        ],
    ),
    "TSXAnalyzer": LanguageCapability(
        language="tsx",
        analyzer="reveal.analyzers.typescript.TSXAnalyzer",
        function_body_shape=(
            "Same as TypeScript plus JSX; lowercase intrinsic tags (<div>) "
            "parse as bare identifier with no distinguishing kind from a "
            "real variable reference — case convention is the only signal "
            "for whether a tag is a real component reference."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=True,
        import_resolution=(
            "Shares JavaScript/TypeScript's bespoke extractor via the "
            ".tsx extension."
        ),
        conformance_level=CONFORMANCE_SMOKE_TESTED,
        known_limitations=[
            "Lowercase JSX intrinsic tags were misread as bogus variable "
            "reads in both the deps-candidate walker and VarFlowWalker "
            "until fixed via excalidraw real-corpus dogfooding (mirrors "
            "Lua's dual-walker fix pattern).",
        ],
    ),
}

# ---------------------------------------------------------------------------
# Tier C — structure-only (tests/test_tier_c.py): confirmed via
# --language-info to expose only "File structure", no nav-flag surface at
# all. Each maps to a real corpus file per LANGUAGE_DOGFOOD_CORPUS_2026-07-02.md.
# ---------------------------------------------------------------------------

_STRUCTURE_ONLY_NOTE = (
    "Confirmed structure-only (--language-info shows only 'File structure', "
    "no nav-flag surface) via tests/test_tier_c.py; only routing + "
    "structure-view + --check non-crash verified against a real corpus "
    "file, no deeper ground truth exists or is claimed."
)

_TIER_C: Dict[str, LanguageCapability] = {
    "BashAnalyzer": LanguageCapability(
        language="bash",
        analyzer="reveal.analyzers.bash.BashAnalyzer",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="No import extractor; not applicable to shell scripts.",
        conformance_level=CONFORMANCE_STRUCTURE_ONLY,
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against Kubernetes' get-kube.sh.",
        ],
    ),
    "DockerfileAnalyzer": LanguageCapability(
        language="dockerfile",
        analyzer="reveal.analyzers.dockerfile.DockerfileAnalyzer",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_STRUCTURE_ONLY,
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real build/pause/Dockerfile "
            "from the Go corpus.",
        ],
    ),
    "SQLAnalyzer": LanguageCapability(
        language="sql",
        analyzer="reveal.analyzers.sql.SQLAnalyzer",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_STRUCTURE_ONLY,
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real AppFlowy migration "
            ".sql file.",
        ],
    ),
    "HCLAnalyzer": LanguageCapability(
        language="hcl",
        analyzer="reveal.analyzers.hcl.HCLAnalyzer",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_STRUCTURE_ONLY,
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real Terraform main.tf "
            "from Kong's corpus.",
        ],
    ),
    "PowerShellAnalyzer": LanguageCapability(
        language="powershell",
        analyzer="reveal.analyzers.powershell.PowerShellAnalyzer",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_STRUCTURE_ONLY,
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real .ps1 from the "
            "TypeScript/vscode corpus.",
        ],
    ),
    "BatchAnalyzer": LanguageCapability(
        language="batch",
        analyzer="reveal.analyzers.batch.BatchAnalyzer",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_STRUCTURE_ONLY,
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real gradlew.bat from "
            "the Java corpus.",
        ],
    ),
    "HTMLAnalyzer": LanguageCapability(
        language="html",
        analyzer="reveal.analyzers.html.HTMLAnalyzer",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_STRUCTURE_ONLY,
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real index.html from "
            "the JavaScript corpus.",
        ],
    ),
    "JupyterAnalyzer": LanguageCapability(
        language="jupyter",
        analyzer="reveal.analyzers.jupyter_analyzer.JupyterAnalyzer",
        function_body_shape="N/A — structure-only (cell-level), no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_STRUCTURE_ONLY,
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real test.ipynb from "
            "the TypeScript/vscode corpus.",
        ],
    ),
}

# ---------------------------------------------------------------------------
# Untested — registered and reachable (or, for two entries, registered in
# source but NOT actually reachable — see their known_limitations) but with
# no conformance matrix entry, no smoke-tier entry, and no tier C mapping.
# Mostly non-code data/config/document formats where varflow has no meaning.
# ---------------------------------------------------------------------------

_NON_CODE_NOTE = (
    "N/A — non-code data/config/document format, no function-body or "
    "variable-flow concept applies."
)

_UNTESTED: Dict[str, LanguageCapability] = {
    "CsvAnalyzer": LanguageCapability(
        language="csv", analyzer="reveal.analyzers.csv_analyzer.CsvAnalyzer",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    ),
    "GraphQLAnalyzer": LanguageCapability(
        language="graphql", analyzer="reveal.analyzers.graphql.GraphQLAnalyzer",
        function_body_shape="N/A — schema/query language, no imperative function bodies.",
        varflow=VARFLOW_NOT_APPLICABLE, imports_unused=None,
        import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    ),
    "IniAnalyzer": LanguageCapability(
        language="ini", analyzer="reveal.analyzers.ini_analyzer.IniAnalyzer",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED,
        known_limitations=[
            "Also registers '.conf' — shadowed by NginxAnalyzer's own "
            "'.conf' registration depending on import order (see "
            "NginxAnalyzer's entry); IniAnalyzer wins in the current "
            "reveal/analyzers/__init__.py import order.",
        ],
    ),
    "JsonAnalyzer": LanguageCapability(
        language="json", analyzer="reveal.analyzers.yaml_json.JsonAnalyzer",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    ),
    "JsonlAnalyzer": LanguageCapability(
        language="jsonl", analyzer="reveal.analyzers.jsonl.JsonlAnalyzer",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    ),
    "MarkdownAnalyzer": LanguageCapability(
        language="markdown", analyzer="reveal.analyzers.markdown.MarkdownAnalyzer",
        function_body_shape="N/A — prose/heading structure, no function-body concept.",
        varflow=VARFLOW_NOT_APPLICABLE, imports_unused=None,
        import_resolution="Not applicable (--links tracks link targets, not imports).",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    ),
    "ProtobufAnalyzer": LanguageCapability(
        language="proto", analyzer="reveal.analyzers.protobuf.ProtobufAnalyzer",
        function_body_shape="N/A — schema/IDL, no imperative function bodies.",
        varflow=VARFLOW_NOT_APPLICABLE, imports_unused=None,
        import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    ),
    "TomlAnalyzer": LanguageCapability(
        language="toml", analyzer="reveal.analyzers.toml.TomlAnalyzer",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    ),
    "XmlAnalyzer": LanguageCapability(
        language="xml", analyzer="reveal.analyzers.xml_analyzer.XmlAnalyzer",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    ),
    "YamlAnalyzer": LanguageCapability(
        language="yaml", analyzer="reveal.analyzers.yaml_json.YamlAnalyzer",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    ),
    "NginxAnalyzer": LanguageCapability(
        language="nginx", analyzer="reveal.analyzers.nginx.NginxAnalyzer",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED,
        known_limitations=[
            "NOT REACHABLE via the registry as of this audit (2026-07-04): "
            "NginxAnalyzer registers only '.conf', and reveal/analyzers/"
            "__init__.py imports nginx.py before ini_analyzer.py, so "
            "IniAnalyzer's later '.conf' registration silently overwrites "
            "it in _ANALYZER_REGISTRY — every .conf file routes to "
            "IniAnalyzer, never NginxAnalyzer, regardless of content. "
            "Noticed during BACK-444, not fixed (out of scope).",
        ],
    ),
    "ElixirAnalyzer": LanguageCapability(
        language="elixir", analyzer="reveal.analyzers.elixir.ElixirAnalyzer",
        function_body_shape="Standard block-nested (do/end blocks).",
        varflow=VARFLOW_UNTESTED, imports_unused=None,
        import_resolution="No import extractor registered.",
        conformance_level=CONFORMANCE_UNTESTED,
        known_limitations=[
            "NOT REACHABLE via the registry in normal CLI use as of this "
            "audit (2026-07-04): reveal/analyzers/elixir.py is never "
            "imported by reveal/analyzers/__init__.py, so its @register "
            "decorator never fires outside of tests that import the module "
            "directly (tests/test_elixir_analyzer.py does, which is why "
            "its own 'test_analyzer_registered' case passes in the full "
            "suite but would fail if run in isolation). In real CLI usage, "
            ".ex/.exs files silently fall through to the generic "
            "tree-sitter fallback. Noticed during BACK-444, not fixed "
            "(out of scope).",
        ],
    ),
}

# ---------------------------------------------------------------------------
# Office document formats (reveal/analyzers/office/*.py) — structure-only
# (paragraphs/sheets/slides), never had a nav-flag surface to test.
# ---------------------------------------------------------------------------

_OFFICE_NOTE = "N/A — office document format, no function-body or variable-flow concept applies."

_OFFICE: Dict[str, LanguageCapability] = {
    name: LanguageCapability(
        language=lang, analyzer=f"reveal.analyzers.office.{module}.{name}",
        function_body_shape=_OFFICE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        conformance_level=CONFORMANCE_UNTESTED, known_limitations=[],
    )
    for name, lang, module in [
        ("DocxAnalyzer", "docx", "openxml"),
        ("XlsxAnalyzer", "xlsx", "openxml"),
        ("PptxAnalyzer", "pptx", "openxml"),
        ("OdtAnalyzer", "odt", "odf"),
        ("OdsAnalyzer", "ods", "odf"),
        ("OdpAnalyzer", "odp", "odf"),
    ]
}

# ---------------------------------------------------------------------------
# Public registry, keyed by analyzer class name (unique, always present —
# unlike the `language` class attribute, which several FileAnalyzer
# subclasses that predate TreeSitterAnalyzer never set).
# ---------------------------------------------------------------------------

CAPABILITIES: Dict[str, LanguageCapability] = {
    **_TIER1, **_SMOKE, **_TIER_C, **_UNTESTED, **_OFFICE,
}


def get_capability(analyzer_cls: Any) -> Optional[LanguageCapability]:
    """Look up the capability profile for an analyzer class (or instance).

    Args:
        analyzer_cls: An analyzer class, or an instance of one.

    Returns:
        The matching LanguageCapability, or None if unregistered.
    """
    cls = analyzer_cls if isinstance(analyzer_cls, type) else type(analyzer_cls)
    return CAPABILITIES.get(cls.__name__)


def get_capability_for_extension(ext: str) -> Optional[LanguageCapability]:
    """Look up the capability profile for a file extension (e.g. '.py').

    Resolves the extension to its registered analyzer class first, so this
    always reflects what the registry would actually dispatch to.
    """
    cls = get_analyzer_mapping().get(ext.lower())
    return get_capability(cls) if cls is not None else None


def get_all_capabilities() -> Dict[str, LanguageCapability]:
    """Return the full capability registry, keyed by analyzer class name."""
    return dict(CAPABILITIES)
