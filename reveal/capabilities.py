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

* ``tier1-verified``   — one of the 13 languages in
  ``tests/test_conformance_matrix.py``: a real fixture + hand-written
  ``expected.yaml`` ground truth checked against every nav flag.
* ``smoke-tested``      — one of the 6 languages in
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

``validation`` (BACK-880) is a further refinement: ``conformance_level``
answers "has this language been through independent-oracle validation at
all?"; ``validation`` answers "what exactly was measured, on what corpus, at
what recall, with what caveats?" — the actual numbers from ``VALIDATION.md``'s
"Validation status at a glance" table, transcribed once here so they're
queryable via ``--capabilities``/``--language-info`` instead of stuck in
prose. See ``MeasuredRecall`` below for the field shape and ``V031``
(``reveal/rules/validation/V031.py``) for the drift check that keeps this
data traceable back to VALIDATION.md's table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import get_analyzer_for_extension

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

# --- measured recall signals (BACK-880) -------------------------------------
#
# ``conformance_level`` above answers "has this language been through the
# independent-oracle validation program at all, and how far?" These constants
# name the three signals VALIDATION.md actually measures recall for, once a
# language has.

RECALL_SIGNAL_IMPORT = "import_recall"
RECALL_SIGNAL_SIDE_EFFECT = "side_effect_recall"
RECALL_SIGNAL_CALL_GRAPH = "call_graph_recall"

_RECALL_SIGNALS = frozenset({
    RECALL_SIGNAL_IMPORT, RECALL_SIGNAL_SIDE_EFFECT, RECALL_SIGNAL_CALL_GRAPH,
})


@dataclass(frozen=True)
class MeasuredRecall:
    """One independently-measured recall data point for a (language, signal)
    pair, transcribed from VALIDATION.md's "Validation status at a glance"
    table (BACK-880). ``conformance_level`` says a language has *some*
    evidence; this says exactly what was measured, against what corpus, and
    with what caveats — the difference VALIDATION.md itself insists matters
    (its own words: "a sample is not a census").

    A signal can have more than one ``MeasuredRecall`` entry (e.g. TypeScript
    import recall was measured on both VS Code and nest, at different
    percentages) — ``LanguageCapability.validation`` is a flat list, not a
    dict keyed by signal, so this is representable without contortion.

    ``sample_note`` is populated only where VALIDATION.md's own "how to read
    this table" caveats explicitly flag a stratified (non-census) sample —
    e.g. Rust/Meilisearch at 295 of 1,491 edges (20%). Its absence means
    "not called out as partial in the summary," not "verified full
    population" — read VALIDATION.md's per-language Results section directly
    for full stratification detail; this registry deliberately does not
    duplicate that level of detail (see module docstring, BACK-880 scoping).
    """

    signal: str  # one of the RECALL_SIGNAL_* constants above
    recall_pct: float  # headline recall — post-fix, if VALIDATION.md shows a before/after arrow
    corpus: str  # e.g. "Home Assistant"; may name more than one corpus
    pre_fix_pct: Optional[float] = None  # set when the table showed "before%→after%"
    sample_note: Optional[str] = None  # explicit stratified-sample caveat, verbatim gist
    fixed_tickets: List[str] = field(default_factory=list)
    open_tickets: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.signal not in _RECALL_SIGNALS:
            raise ValueError(
                f"signal={self.signal!r} not one of {sorted(_RECALL_SIGNALS)}"
            )


@dataclass(frozen=True)
class LanguageCapability:
    """A machine-readable profile of what reveal actually knows to be true
    about one language's analysis quality.

    Fields match the shape specified in BACK-444 (internal-docs/BACKLOG.md).
    """

    language: str
    function_body_shape: str
    varflow: str  # one of the VARFLOW_* levels above
    imports_unused: Optional[bool]
    import_resolution: str
    conformance_level: str  # one of the CONFORMANCE_* levels above
    known_limitations: List[str] = field(default_factory=list)
    validation: List[MeasuredRecall] = field(default_factory=list)  # BACK-880

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
# Per-tier factories: conformance_level is 100% determined by which tier an
# entry belongs to (BACK-456 item 1), so it is stamped once here rather than
# repeated as a literal on every one of the ~43 entries below.
# ---------------------------------------------------------------------------

def _tier1(**kwargs: Any) -> LanguageCapability:
    return LanguageCapability(conformance_level=CONFORMANCE_TIER1_VERIFIED, **kwargs)


def _smoke(**kwargs: Any) -> LanguageCapability:
    return LanguageCapability(conformance_level=CONFORMANCE_SMOKE_TESTED, **kwargs)


def _tier_c(**kwargs: Any) -> LanguageCapability:
    return LanguageCapability(conformance_level=CONFORMANCE_STRUCTURE_ONLY, **kwargs)


def _untested(**kwargs: Any) -> LanguageCapability:
    return LanguageCapability(conformance_level=CONFORMANCE_UNTESTED, **kwargs)


# ---------------------------------------------------------------------------
# Tier 1 — deep conformance matrix (tests/test_conformance_matrix.py, 13
# languages, fixture + expected.yaml ground truth for every nav flag).
# Kotlin/Swift/Ruby/PHP promoted from the smoke tier (BACK-477, resoyere-0707)
# once all four gained real fixtures + expected.yaml ground truth in the
# conformance matrix — every catalogued nav-layer gap closed and regression-pinned.
# ---------------------------------------------------------------------------

_TIER1: Dict[str, LanguageCapability] = {
    "PythonAnalyzer": _tier1(
        language="python",
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
        known_limitations=[],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Home Assistant, celery"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 83.5, "Home Assistant"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "Home Assistant",
                            pre_fix_pct=99.96, sample_note="3 query directions"),
        ],
    ),
    "RustAnalyzer": _tier1(
        language="rust",
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
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Meilisearch, ripgrep"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 97.4, "Meilisearch"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "Meilisearch",
                            pre_fix_pct=95.27, sample_note="295 of 1,491 edges (20%), stratified by fan-in",
                            fixed_tickets=["BACK-733"]),
        ],
    ),
    "GoAnalyzer": _tier1(
        language="go",
        function_body_shape="Standard block-nested, C-shaped.",
        varflow=VARFLOW_VERIFIED,
        imports_unused=True,
        import_resolution=(
            "Bespoke extractor (imports/go.py) resolves within-module import "
            "paths; fixed BACK-431 Issue G to derive the local package name "
            "from the segment before a semantic-import-versioning /vN "
            "suffix (e.g. k8s.io/klog/v2 -> klog, not v2)."
        ),
        known_limitations=[
            "BACK-451 (open): named `Class.method` extraction syntax fails "
            "for Go — methods are free functions with a receiver parameter, "
            "not nested under a type body, so literal Class.method syntax "
            "may never apply; `:LINE-RANGE` is the working workaround.",
        ],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Kubernetes, client_golang"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 96.3, "client-go"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "Go compiler internals"),
        ],
    ),
    "CAnalyzer": _tier1(
        language="c",
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
        known_limitations=[],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Redis, curl"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 92.0, "Redis",
                            sample_note="`http` category declined"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "Redis",
                            pre_fix_pct=89.52, open_tickets=["BACK-756"]),
        ],
    ),
    "CppAnalyzer": _tier1(
        language="cpp",
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
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Godot, assimp"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 83.3, "Godot"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 95.73, "assimp",
                            sample_note="Godot sample 450 of 7,230 oracle edges (6.2%)"),
        ],
    ),
    "JavaAnalyzer": _tier1(
        language="java",
        function_body_shape=(
            "Standard block-nested; annotations, field_access, and "
            "method_invocation all needed explicit member-access/"
            "compile-time-only exclusions (fixed BACK-431 Issue G) to avoid "
            "misreading class/field/method names as variable reads."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=False,
        import_resolution=(
            "Generic extractor (imports/generic.py). Resolves same-project "
            "file edges (BACK-487): `import com.pkg.Type` → com/pkg/Type.java "
            "by package-path suffix (reliable, javac enforces package==dir); "
            "wildcard/static imports and JDK classes skip. Unused-detection "
            "not claimed."
        ),
        known_limitations=[],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Elasticsearch, guava"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 97.5, "Elasticsearch"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "Elasticsearch",
                            pre_fix_pct=9.99, fixed_tickets=["BACK-734"]),
        ],
    ),
    "CSharpAnalyzer": _tier1(
        language="csharp",
        function_body_shape="Standard block-nested.",
        varflow=VARFLOW_VERIFIED,
        imports_unused=False,
        import_resolution=(
            "Generic extractor (imports/generic.py); listing always. File-edge "
            "resolution is sparse by nature (BACK-487): `using X.Y` imports a "
            "namespace — a directory of files — not one type, so an edge "
            "resolves only when a matching Y.cs happens to exist; full C# "
            "fan-in needs a namespace-declaration index (tracked separately). "
            "Unused-detection not claimed."
        ),
        known_limitations=[
            "imports:// file-level fan-in is largely empty for C#: `using` "
            "names namespaces, not files, so most imports honestly skip rather "
            "than fabricate an edge. Needs a namespace→declaring-files index.",
        ],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Jellyfin"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 99.36, "Newtonsoft.Json",
                            fixed_tickets=["BACK-702"]),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 98.3, "Jellyfin"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "Jellyfin",
                            pre_fix_pct=69.74, fixed_tickets=["BACK-737"]),
        ],
    ),
    "JavaScriptAnalyzer": _tier1(
        language="javascript",
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
        known_limitations=[],
        validation=[
            # VALIDATION.md's summary table reports "TSX, plain JS" as one
            # combined row (three.js is plain JS, Excalidraw/react-router are
            # TSX) — duplicated onto both JavaScriptAnalyzer and TSXAnalyzer
            # since the table doesn't split them, corpus names preserved so
            # the actual per-corpus language is honest.
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Excalidraw, three.js"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "react-router"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 98.4, "Excalidraw"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "three.js, Excalidraw",
                            fixed_tickets=["BACK-751", "BACK-752"]),
        ],
    ),
    "TypeScriptAnalyzer": _tier1(
        language="typescript",
        function_body_shape=(
            "Same as JavaScript plus type annotations/interfaces; arrow-"
            "function extraction now lives on the shared base, not a "
            "TypeScript-only override."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=True,
        import_resolution="Same bespoke extractor as JavaScript.",
        known_limitations=[],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "VS Code"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 99.93, "nest",
                            pre_fix_pct=68.48,
                            sample_note="2-edge unexplored residual",
                            fixed_tickets=["BACK-694", "BACK-698", "BACK-705", "BACK-772", "BACK-773"]),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 91.3, "VS Code"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "VS Code"),
        ],
    ),
    "KotlinAnalyzer": _tier1(
        language="kotlin",
        function_body_shape=(
            "Expression-oriented if/when (when_expression/when_entry, "
            "fully fieldless); property_declaration exposes no fields at "
            "all, unlike Swift's node of the same name."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=None,
        import_resolution=(
            "Generic extractor (imports/generic.py), added BACK-488. Resolves "
            "`import com.pkg.Bar` → com/pkg/Bar.kt by package-path suffix when "
            "the file is named for the class; wildcards skip. Kotlin does not "
            "enforce filename==classname, so resolution is best-effort (honest "
            "skip otherwise). Unused-detection not claimed."
        ),
        known_limitations=[
            "import→file resolution assumes filename==classname; an import of "
            "a class living in a differently-named .kt file honestly skips "
            "rather than fabricate an edge.",
        ],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 99.1, "tivi"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "kotlinx.coroutines"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 92.9, "tivi",
                            pre_fix_pct=82.5, sample_note="six-category sweep",
                            fixed_tickets=["BACK-727"]),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 99.69, "tivi",
                            sample_note="8/bucket sampling"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 99.79, "tivi",
                            sample_note="20/bucket sampling",
                            open_tickets=["BACK-738 (tree-sitter grammar bug, not fixable in reveal)"]),
        ],
    ),
    "SwiftAnalyzer": _tier1(
        language="swift",
        function_body_shape=(
            "Identifiers parse as simple_identifier (unique among reveal's "
            "languages); switch_entry case arms and the leading-dot "
            "implicit-member shorthand (.someCase) are fieldless."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=None,
        import_resolution=(
            "Generic extractor (imports/generic.py), added BACK-488. `import "
            "Foo` resolves to Foo.swift only where a module maps 1:1 to a lone "
            "in-tree file; system frameworks (Foundation, UIKit) and "
            "multi-file modules honestly skip, so Swift fan-in is sparse. "
            "Unused-detection not claimed."
        ),
        known_limitations=[
            "import→file edges are sparse: Swift modules rarely map 1:1 to a "
            "single in-tree file, so most imports honestly skip rather than "
            "fabricate an edge.",
        ],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Kickstarter iOS",
                            sample_note="module-index target-resolution coverage, not an edge-recall ratio"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 98.42, "swift-collections",
                            sample_note="14,824 edges", fixed_tickets=["BACK-704"]),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 100.0, "Kickstarter iOS",
                            pre_fix_pct=43.3, sample_note="six-category sweep",
                            fixed_tickets=["BACK-728"]),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 97.62, "Signal-iOS",
                            sample_note="8/bucket sampling"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 99.79, "Signal-iOS",
                            sample_note="20/bucket sampling",
                            open_tickets=["BACK-742 (two tree-sitter grammar bugs, not fixable in reveal)"]),
        ],
    ),
    "RubyAnalyzer": _tier1(
        language="ruby",
        function_body_shape=(
            "Paren-less method defs (def human? ... end, no parens at all); "
            "implicit last-expression return, statement modifiers "
            "(return x if y)."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=False,
        import_resolution=(
            "Generic extractor (imports/generic.py) with call-style "
            "require/require_relative support. Resolves same-project edges "
            "(BACK-487): `require_relative './x'` → x.rb relative to the file, "
            "`load 'lib/y.rb'` when it names a real in-tree .rb; bare "
            "`require 'json'` (a gem) skips. Unused-detection not claimed "
            "(skip_unused always set)."
        ),
        known_limitations=[],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "solidus",
                            sample_note="Zeitwerk-inferred", fixed_tickets=["BACK-700", "BACK-701"]),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 98.8, "Discourse"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "Discourse",
                            pre_fix_pct=22.05, fixed_tickets=["BACK-735"]),
        ],
    ),
    "PhpAnalyzer": _tier1(
        language="php",
        function_body_shape=(
            "elseif_clause sits in _GATE_NODE_TYPES but was historically "
            "absent from SCOPE_NODES/KEYWORD_LABEL (BACK-431 Issue G flagged "
            "the drift); case_statement/default_statement are the real "
            "switch-arm kinds (the switch_case/switch_default placeholders "
            "previously in the taxonomy matched no real PHP parse)."
        ),
        varflow=VARFLOW_VERIFIED,
        imports_unused=False,
        import_resolution=(
            "Generic extractor (imports/generic.py) with require/include "
            "statement + call-style support. Resolves same-project edges "
            "(BACK-487): `use App\\Models\\User` → .../Models/User.php by "
            "longest-unique path-suffix (tolerant of the PSR-4 vendor-root "
            "prefix, ambiguous basenames skip), and `require 'lib/x.php'` "
            "relative to the file. Unused-detection not claimed."
        ),
        known_limitations=[],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "WordPress"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 74.65, "osCommerce"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 97.5, "WordPress"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "WordPress",
                            pre_fix_pct=98.87, fixed_tickets=["BACK-736"]),
        ],
    ),
}

# ---------------------------------------------------------------------------
# Tier A/B — smoke tier (tests/test_smoke_tier.py): every nav flag asserted
# non-crashing/non-empty, backed by at least one real-corpus dogfood pass,
# but with no expected.yaml ground truth.
# ---------------------------------------------------------------------------

_SMOKE: Dict[str, LanguageCapability] = {
    "ScalaAnalyzer": _smoke(
        language="scala",
        function_body_shape=(
            "val_definition/var_definition declarations; enumerator "
            "(for-comprehension bindings) is one fieldless node kind "
            "covering 3 shapes (generator/value/guard); throw parses as "
            "throw_expression, not throw_statement."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=None,
        import_resolution="No import extractor registered.",
        known_limitations=[
            "val/var_definition WRITE-as-READ mislabeling and "
            "throw_expression invisibility to --exits/--returns were "
            "found+fixed via smoke + real-corpus (gitbucket) dogfooding.",
            "Named call arguments (f(x = value)) parse as "
            "assignment_expression, structurally identical to a real "
            "reassignment — fixed with an arguments-node-aware branch.",
        ],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "GitBucket",
                            sample_note="n=1 qualifying edge"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "cats-effect",
                            sample_note="24 edges"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 66.3, "GitBucket",
                            sample_note="`db`/Slick categories declined"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "GitBucket",
                            pre_fix_pct=96.64, fixed_tickets=["BACK-746", "BACK-747"]),
        ],
    ),
    "DartAnalyzer": _smoke(
        language="dart",
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
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 99.76, "AppFlowy",
                            sample_note="residual is oracle false positives, 100% of real edges"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 96.63, "drift",
                            sample_note="residual is oracle false positives, 100% of real edges"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 84.9, "AppFlowy",
                            sample_note="bare File/Directory declined"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 97.55, "AppFlowy",
                            pre_fix_pct=100.0,
                            fixed_tickets=["BACK-760", "BACK-761", "BACK-763", "BACK-764",
                                           "BACK-765", "BACK-766", "BACK-767", "BACK-769"],
                            open_tickets=["BACK-768 (tree-sitter grammar bug, not fixable in reveal)"]),
        ],
    ),
    "LuaAnalyzer": _smoke(
        language="lua",
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
        known_limitations=[
            "VarFlowWalker (used directly by --varflow) lacked "
            "member-access exclusion generally — found via Kong real-corpus "
            "dogfooding, fixed generally for every language including "
            "Python.",
            "function table.name(...) had no name at all before the "
            "dotted-segment fallback fix (a common Kong-style public-API "
            "pattern).",
        ],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 99.87, "Kong"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 99.33, "AwesomeWM"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 98.0, "Kong",
                            sample_note="`truncate`/`connect` categories declined"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "Kong",
                            fixed_tickets=["BACK-757", "BACK-758"]),
        ],
    ),
    "ZigAnalyzer": _smoke(
        language="zig",
        function_body_shape=(
            "Entirely fieldless grammar — no child_by_field_name support "
            "anywhere; Decl/FnProto (not function_definition) needs its own "
            "extractor; SuffixExpr packs an entire dotted-call chain into "
            "one node's children rather than nesting."
        ),
        varflow=VARFLOW_SMOKE_TESTED,
        imports_unused=None,
        import_resolution="No import extractor registered.",
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
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "ghostty"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "TigerBeetle"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 98.4, "TigerBeetle"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 99.98, "ghostty",
                            pre_fix_pct=92.28,
                            sample_note="426 of 2,334 edges (18%), stratified by fan-in",
                            fixed_tickets=["BACK-753", "BACK-754", "BACK-755"]),
        ],
    ),
    "GDScriptAnalyzer": _smoke(
        language="gdscript",
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
        known_limitations=[
            "var x = f() was invisible to --varflow entirely until the "
            "name-kind leaf case was added (found via the smoke fixture).",
            "--calls was partially blind to attribute_call dotted calls "
            "until fixed via godot-demo-projects real-corpus dogfooding; "
            "--deps was already clean.",
        ],
        validation=[
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "godot-demo-projects"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Pixelorama"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 69.3, "Pixelorama",
                            sample_note="bare `print`/`request` categories declined"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "Pixelorama",
                            fixed_tickets=["BACK-759"]),
        ],
    ),
    "TSXAnalyzer": _smoke(
        language="tsx",
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
        known_limitations=[
            "Lowercase JSX intrinsic tags were misread as bogus variable "
            "reads in both the deps-candidate walker and VarFlowWalker "
            "until fixed via excalidraw real-corpus dogfooding (mirrors "
            "Lua's dual-walker fix pattern).",
        ],
        validation=[
            # Same combined "TSX, plain JS" row as JavaScriptAnalyzer above —
            # see the note there.
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "Excalidraw, three.js"),
            MeasuredRecall(RECALL_SIGNAL_IMPORT, 100.0, "react-router"),
            MeasuredRecall(RECALL_SIGNAL_SIDE_EFFECT, 98.4, "Excalidraw"),
            MeasuredRecall(RECALL_SIGNAL_CALL_GRAPH, 100.0, "three.js, Excalidraw",
                            fixed_tickets=["BACK-751", "BACK-752"]),
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
    "BashAnalyzer": _tier_c(
        language="bash",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="No import extractor; not applicable to shell scripts.",
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against Kubernetes' get-kube.sh.",
        ],
    ),
    "DockerfileAnalyzer": _tier_c(
        language="dockerfile",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real build/pause/Dockerfile "
            "from the Go corpus.",
        ],
    ),
    "SQLAnalyzer": _tier_c(
        language="sql",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real AppFlowy migration "
            ".sql file.",
        ],
    ),
    "HCLAnalyzer": _tier_c(
        language="hcl",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real Terraform main.tf "
            "from Kong's corpus.",
        ],
    ),
    "PowerShellAnalyzer": _tier_c(
        language="powershell",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real .ps1 from the "
            "TypeScript/vscode corpus.",
        ],
    ),
    "BatchAnalyzer": _tier_c(
        language="batch",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real gradlew.bat from "
            "the Java corpus.",
        ],
    ),
    "HTMLAnalyzer": _tier_c(
        language="html",
        function_body_shape="N/A — structure-only, no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
        known_limitations=[
            _STRUCTURE_ONLY_NOTE + " Verified against a real index.html from "
            "the JavaScript corpus.",
        ],
    ),
    "JupyterAnalyzer": _tier_c(
        language="jupyter",
        function_body_shape="N/A — structure-only (cell-level), no nav-flag dispatch surface.",
        varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None,
        import_resolution="Not applicable.",
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
    "CsvAnalyzer": _untested(
        language="csv",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
 known_limitations=[],
    ),
    "GraphQLAnalyzer": _untested(
        language="graphql",
        function_body_shape="N/A — schema/query language, no imperative function bodies.",
        varflow=VARFLOW_NOT_APPLICABLE, imports_unused=None,
        import_resolution="Not applicable.",
 known_limitations=[],
    ),
    "IniAnalyzer": _untested(
        language="ini",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        known_limitations=[
            "Also registers '.conf' — shadowed by NginxAnalyzer's own "
            "'.conf' registration depending on import order (see "
            "NginxAnalyzer's entry); IniAnalyzer wins in the current "
            "reveal/analyzers/__init__.py import order.",
        ],
    ),
    "JsonAnalyzer": _untested(
        language="json",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
 known_limitations=[],
    ),
    "JsonlAnalyzer": _untested(
        language="jsonl",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
 known_limitations=[],
    ),
    "MarkdownAnalyzer": _untested(
        language="markdown",
        function_body_shape="N/A — prose/heading structure, no function-body concept.",
        varflow=VARFLOW_NOT_APPLICABLE, imports_unused=None,
        import_resolution="Not applicable (--links tracks link targets, not imports).",
 known_limitations=[],
    ),
    "ProtobufAnalyzer": _untested(
        language="proto",
        function_body_shape="N/A — schema/IDL, no imperative function bodies.",
        varflow=VARFLOW_NOT_APPLICABLE, imports_unused=None,
        import_resolution="Not applicable.",
 known_limitations=[],
    ),
    "TomlAnalyzer": _untested(
        language="toml",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
 known_limitations=[],
    ),
    "XmlAnalyzer": _untested(
        language="xml",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
 known_limitations=[],
    ),
    "YamlAnalyzer": _untested(
        language="yaml",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
 known_limitations=[],
    ),
    "NginxAnalyzer": _untested(
        language="nginx",
        function_body_shape=_NON_CODE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        known_limitations=[
            "REACHABLE via real CLI dispatch (registry.get_analyzer()): "
            "_try_conf_detection() content/path-sniffs '.conf' files and "
            "routes nginx-shaped ones to NginxAnalyzer *before* the plain "
            "extension-table lookup runs, so real analysis is correct "
            "(verified 2026-07-04, BACK-455). What IS true: "
            "_ANALYZER_REGISTRY['.conf'] itself (a single dict slot) can "
            "only hold one class, and IniAnalyzer's import in reveal/"
            "analyzers/__init__.py registers '.conf' after NginxAnalyzer, "
            "so it wins that slot — any caller that reads the registry "
            "directly instead of going through get_analyzer() (this "
            "module's get_capability_for_extension('.conf'), "
            "get_analyzer_mapping(), 'reveal --languages') sees IniAnalyzer "
            "only. That's a structural limit of one-class-per-extension "
            "metadata, not a routing bug — content-dependent dispatch has "
            "no single 'the' analyzer to report for '.conf'.",
        ],
    ),
    "ElixirAnalyzer": _untested(
        language="elixir",
        function_body_shape=(
            "Everything is a macro *call*: `def add(a,b) do … end` parses as a "
            "`call` node whose first child is `identifier('def')`, not a "
            "distinct function_definition kind. `_extract_functions`/"
            "`_extract_classes`/`extract_element` are overridden to match on "
            "the leading macro keyword (def/defp/defmacro/defguard/defdelegate "
            "→ functions, defmodule → class) and read the name out of the "
            "call's `arguments` (handles zero-arg, `when` guards, single-line "
            "`, do:` clauses, and `Foo.Bar` aliases). BACK-480."
        ),
        varflow=VARFLOW_UNTESTED, imports_unused=None,
        import_resolution="No import extractor registered (imports:// listing/graph not claimed for Elixir).",
        known_limitations=[
            "Structure extraction (functions, modules), element extraction "
            "(`reveal file.ex <name>`), and complexity now work (BACK-480, "
            "extragalactic-journey-0706). Still `[untested]` tier: the "
            "nav-flag surface (--varflow/--sideeffects/--catchmap/…) has no "
            "ground-truth fixtures yet.",
            "`calls`/complexity walk the whole `def` call (signature + body), "
            "so the def's own name and control-flow macros (case/if/cond/with) "
            "appear in a function's `calls` list — inherent to Elixir's "
            "fully call-shaped grammar; correct for complexity (they are real "
            "branch points), mildly noisy for calls://.",
        ],
    ),
}

# ---------------------------------------------------------------------------
# Office document formats (reveal/analyzers/office/*.py) — structure-only
# (paragraphs/sheets/slides), never had a nav-flag surface to test.
# ---------------------------------------------------------------------------

_OFFICE_NOTE = "N/A — office document format, no function-body or variable-flow concept applies."

_OFFICE: Dict[str, LanguageCapability] = {
    name: _untested(
        language=lang,
        function_body_shape=_OFFICE_NOTE, varflow=VARFLOW_NOT_APPLICABLE,
        imports_unused=None, import_resolution="Not applicable.",
        known_limitations=[],
    )
    for name, lang in [
        ("DocxAnalyzer", "docx"),
        ("XlsxAnalyzer", "xlsx"),
        ("PptxAnalyzer", "pptx"),
        ("OdtAnalyzer", "odt"),
        ("OdsAnalyzer", "ods"),
        ("OdpAnalyzer", "odp"),
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
    cls = get_analyzer_for_extension(ext)
    return get_capability(cls) if cls is not None else None


def get_all_capabilities() -> Dict[str, LanguageCapability]:
    """Return the full capability registry, keyed by analyzer class name."""
    return dict(CAPABILITIES)


def capability_tiers_for(language_extensions: Dict[str, str]) -> Dict[str, str]:
    """Map ``{language_key: representative_extension}`` (as produced by
    ``path_utils.ScopeCensus.language_extensions``) to
    ``{language_key: conformance_level}``.

    Command-layer join point for BACK-884's scope census: keeps
    ``path_utils.py``/``results.py`` ignorant of this module (design doc
    BACK884_COVERAGE_CENSUS_UNIFICATION finding #6) while still letting
    ``overview``/``architecture``/``surface``/``check`` attach a
    per-language capability tier to their ``scope`` block.
    """
    tiers = {}
    for lang, ext in language_extensions.items():
        cap = get_capability_for_extension(ext)
        tiers[lang] = cap.conformance_level if cap else 'unknown'
    return tiers


def scope_dict_for_path(path: Path) -> Dict[str, Any]:
    """The BACK-884 ``scope`` block for *path*: a fresh census
    (``path_utils.census_for_path``) with per-language capability tier
    joined in.

    Single shared implementation for commands with no pre-collected file
    list of their own (``overview``, ``architecture``) — importing
    ``path_utils`` here rather than the reverse keeps ``path_utils.py``
    ignorant of this module (finding #6) while still giving both callers
    one function instead of a copy-pasted ``_run_scope`` each.
    """
    from .utils.path_utils import census_for_path

    census = census_for_path(path)
    return census.to_scope_dict(capability_tiers=capability_tiers_for(census.language_extensions))
