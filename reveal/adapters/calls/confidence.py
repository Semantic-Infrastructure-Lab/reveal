"""calls:// meta (confidence/warnings) computation — BACK-1198.

Previously calls:// emitted a single hardcoded ``confidence: 0.85`` and a
Python-vocabulary "dynamic dispatch" warning, unconditionally, regardless of
the language(s) being scanned — identical output for a language reveal has
measured at 100% call-graph extraction recall and one with real, documented
residual gaps. Split into its own module (out of adapter.py) once it grew
past a few constants, to keep adapter.py under reveal's own file-length gate.

See ``defaults.CALL_GRAPH_EXTRACTION_CONFIDENCE`` for where the per-language
numbers come from (the lowest recall in reveal's committed oracle snapshot, BACK-2105).
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ...analyzers._capability_table import calls_extraction_confidence
from ...defaults import (
    CALL_GRAPH_DYNAMIC_DISPATCH_VOCAB,
    CALL_GRAPH_DEFAULT_DISPATCH_VOCAB,
    CALL_GRAPH_IMPLICIT_EXCLUSION_VOCAB,
    CALL_GRAPH_DEFAULT_IMPLICIT_EXCLUSION_VOCAB,
)
from ...utils.path_utils import HiddenTally, OnHidden, census_for_path, hidden_entries_warning, failure_of
from ..ast.analysis import analysis_skipped_warning, function_values_dropped_warning, traversal_failed_warning
from ...reveal_types import PathFailure

# Capability metadata for v1.1 contract (BACK-307).
# Call-graph analysis is static — these limitations are universal across queries.
# Index 0's message is rewritten per-request by build_meta() below to name the
# scanned path's actual dominant-language dispatch idioms.
_CALL_GRAPH_WARNINGS = [
    {'code': 'W-CALLS-1',
     'message': 'Dynamic dispatch (callbacks, getattr, runtime polymorphism) is not resolved.'},
    {'code': 'W-CALLS-2', 'message': 'Method resolution order (MRO) is not considered.'},
    {'code': 'W-CALLS-3', 'message': 'Calls via importlib/dynamic imports are not tracked.'},
    {'code': 'W-CALLS-4',
     'message': 'Calls inside string-evaluated code (eval/exec) are not detected.'},
]

# BACK-1198: "derived signal" caveat, distinct from the extraction-confidence
# warnings above — only attached to ?uncalled results. A zero-callers count
# is not itself a measured signal; it's DERIVED from call extraction plus
# every convention-invoked call no static tool sees (constructors invoked by
# the language runtime, e.g. Ruby's `.new` -> `initialize`; framework
# lifecycle hooks; dynamic dispatch). Reporting one confidence number for
# both extraction accuracy and "is this really dead code" was the actual
# modelling error this ticket found; BACK-2195 (D8) withholds the number for
# ?uncalled in every language.
_UNCALLED_DERIVED_SIGNAL_WARNING = {
    'code': 'W-CALLS-5',
    'message': (
        "'Uncalled' is a derived heuristic, not a separately measured "
        "signal, so it carries no confidence: call extraction is measured, "
        "dead code is not, and every convention-invoked call static analysis "
        "cannot see (runtime constructors, framework lifecycle hooks, "
        "dynamic dispatch) is also missing. "
        "Zero callers found is not proof of dead code."
    ),
}


# The languages a per-language recall snapshot measures (calls-recall-oracle, 19 pairs:
# javascript has two corpora; tsx is scored inside the typescript corpus, whose 307 files
# are .ts/.tsx).
SNAPSHOT_LANGUAGES = frozenset({
    'python', 'typescript', 'tsx', 'javascript', 'go', 'rust', 'java', 'ruby', 'php', 'csharp',
    'kotlin', 'swift', 'cpp', 'c', 'scala', 'zig', 'lua', 'gdscript', 'dart'})

# The languages with no snapshot whose extractor yields call sources: one of their files in scope
# withholds the answer's confidence and is named (decision i, BACK-2066). A language whose files
# yield no call edge (bash, sql, graphql, proto, yaml, ...) does not. Nothing derives this at
# request time: call extraction walks treesitter.CALL_NODE_TYPES (kotlin and zig add their own),
# so a grammar with none of those kinds cannot yield a call, and the grammars that have one were
# checked with a function-calls-function file each (erlang, ocaml, r, verilog and hcl yield no call
# source). tests/test_calls_params_back2066.py re-derives the set from the registered grammars and
# those files, so a new call grammar or a better extractor fails it until it is listed here.
UNMEASURED_CALL_SOURCE_LANGUAGES = frozenset({'elixir', 'objc'})

# Callee walks beyond depth 1 and --detail: no oracle scores them in any language (decision f).
_UNMEASURED_WALK_WARNING = {
    'code': 'W-CALLS-9', 'type': 'not_measured',
    'message': ('Callee walks beyond depth 1 and --detail params/effects are not measured in any language: '
                'the callees snapshot scores depth-1 call lists only.'),
}


def _unmeasured_language_warning(per_language: Dict[str, int]) -> Optional[Dict[str, Any]]:
    """W-CALLS-10, naming each scanned language that yields call sources and has no recall
    snapshot, or None."""
    unmeasured = sorted(lang for lang in per_language if lang in UNMEASURED_CALL_SOURCE_LANGUAGES)
    if not unmeasured:
        return None
    named = ', '.join(f"{lang} ({per_language[lang]} file{'s' if per_language[lang] != 1 else ''})"
                      for lang in unmeasured)
    return {'code': 'W-CALLS-10', 'type': 'not_measured', 'languages': unmeasured,
            'message': (f'Confidence withheld: {named} in scope with no recall snapshot; '
                        'no measured number covers their call edges.')}


# No source file counted in scope (an empty directory, only non-code files, or every file hidden by
# .gitignore): the confidence is a file-weighted mean, and with no file there is nothing to weight,
# so the language-agnostic default would read as measured (BACK-2106).
_EMPTY_CENSUS_WARNING = {
    'code': 'W-CALLS-12', 'type': 'not_measured',
    'message': ('Confidence withheld: the language census counted no source file in scope, '
                'so no measured recall figure applies.'),
}


def _census_unavailable_warning(cause: str) -> Dict[str, Any]:
    """W-CALLS-12 for a census that could not be taken, which is not one that counted no file (BACK-2248):
    the walk failed outside directory enumeration, so nothing is known about the scope's languages.
    *cause* is ``failure_of``'s, the class and reason without the path."""
    return {'code': 'W-CALLS-12', 'type': 'not_measured',
            'message': (f'Confidence withheld: the language census could not be taken ({cause}), '
                        'so no measured recall figure applies.')}


# ?uncalled dead-code precision, measured by source review (BACK-1899, VALIDATION.md): 20 claims per
# corpus, one to three corpora per language. The calls confidence is extraction recall and says nothing
# about it. Each family contributes one sentence, shown only when a language of that family is in scope.
_UNCALLED_MEASURED_LOW = (
    (frozenset({'javascript', 'typescript', 'tsx'}),
     'JavaScript/TypeScript: 0 of 20 (three.js), 12 of 20 (VS Code) and 1 of 20 (Excalidraw) uncalled claims '
     'were dead; public API, framework hooks, class-field initializers, decorators and string-keyed dispatch '
     'read as dead.'),
    (frozenset({'java'}),
     'Java: 1 of 20 (Elasticsearch server, scanned in server/src/main/java only; the other 19 are used '
     'elsewhere in the repo) and 1 of 20 (Guava) were dead; Caliper benchmarks, methods dispatched by an '
     'annotation read outside the scan, methods looked up by name, fixtures read by reflection and callers outside the '
     'scanned directory read as dead.'),
    (frozenset({'php'}),
     'PHP: 1 of 20 (WordPress) were dead; public API, deprecated shims and interface methods read as '
     'dead.'),
)
UNCALLED_MEASURED_LOW_LANGUAGES = frozenset().union(*(langs for langs, _ in _UNCALLED_MEASURED_LOW))


def _uncalled_measured_low_warning(per_language: Dict[str, int]) -> Optional[Dict[str, Any]]:
    """W-CALLS-11, naming each scanned language whose dead-code claims were measured low and stating
    the figures of only those families, or None."""
    named = sorted(lang for lang in per_language if lang in UNCALLED_MEASURED_LOW_LANGUAGES)
    if not named:
        return None
    figures = ' '.join(text for langs, text in _UNCALLED_MEASURED_LOW if langs.intersection(named))
    return {'code': 'W-CALLS-11', 'type': 'not_measured', 'languages': named,
            'message': ('Confidence withheld: dead-code precision is measured low. In a 20-claim source '
                        f'review per corpus, {figures} Treat this as a review list, not findings.')}


def _declines(per_language: Dict[str, int], unmeasured_walk: bool, uncalled: bool = False,
              census_unavailable: Optional[str] = None) -> List[Dict[str, Any]]:
    """W-CALLS-9 for an unmeasured walk, W-CALLS-10 for unmeasured languages, W-CALLS-11 for
    ?uncalled over a language whose dead-code claims were measured low, W-CALLS-12 for a census
    that counted no file (rule 8) or, naming *census_unavailable*, one that could not be taken."""
    declines = [dict(_UNMEASURED_WALK_WARNING)] if unmeasured_walk else []
    unmeasured = _unmeasured_language_warning(per_language)
    measured_low = _uncalled_measured_low_warning(per_language) if uncalled else None
    empty = None if sum(per_language.values()) else (
        _census_unavailable_warning(census_unavailable) if census_unavailable else dict(_EMPTY_CENSUS_WARNING))
    return declines + [w for w in (unmeasured, measured_low, empty) if w]


# The declines that withhold the number (W-CALLS-9 qualifies the walk, not the figure).
_WITHHOLDING_DECLINES = frozenset({'W-CALLS-10', 'W-CALLS-11', 'W-CALLS-12'})


def _reported_confidence(confidence: Optional[float], known_loss: bool, declines: List[Dict[str, Any]],
                         uncalled: bool = False) -> Optional[float]:
    """No number while evidence was lost, a scanned call-source language has no recall snapshot, the
    census counted no file, or the request is ?uncalled (the figure is call-extraction recall, not a
    measure of dead code; D8)."""
    if uncalled or known_loss or any(w['code'] in _WITHHOLDING_DECLINES for w in declines):
        return None
    return confidence


def language_census(path: str, *,
                    on_error: Optional[Callable[[OSError], None]] = None,
                    on_hidden: Optional[OnHidden] = None,
                    on_unavailable: Optional[Callable[[OSError], None]] = None) -> Dict[str, int]:
    """Per-language file counts under *path* (BACK-1198) — single walk,
    shared by the confidence and dynamic-dispatch-vocabulary computation.
    Empty dict (not an exception) on a missing/unreadable path — callers
    fall back to the language-agnostic defaults, same as the "unmeasured
    language" case. The optional callback retains actual directory enumeration
    errors; the broad fallback below also covers unqualified non-walk errors.
    *on_hidden* sees what the walk hid (BACK-2065). *on_unavailable* sees the error behind that
    fallback ``{}`` (BACK-2248): not a lost directory (BACK-2027), but not an empty scope either.
    """
    try:
        return dict(census_for_path(Path(path), on_error=on_error, on_hidden=on_hidden).per_language)
    except OSError as error:
        if on_unavailable is not None:
            on_unavailable(error)
        return {}


def build_meta(path: str, *, uncalled: bool = False, unmeasured_walk: bool = False,
               skipped: Sequence[Tuple[str, str]] = (),
               traversal_failures: Sequence[PathFailure] = (),
               census: Optional[Dict[str, int]] = None,
               dropped: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Per-request calls:// meta kwargs (BACK-1198).

    Replaces the prior flat ``confidence: 0.85`` (identical for a language
    measured at 100% extraction recall and one with real residual gaps) with
    a file-count-weighted average of the per-language figures reveal has
    actually measured (``defaults.CALL_GRAPH_EXTRACTION_CONFIDENCE``), and
    swaps the generic "dynamic dispatch... getattr..." warning (Python
    vocabulary, printed unconditionally on every language) for the dominant
    language's own dispatch idioms. A scanned language in UNMEASURED_CALL_SOURCE_LANGUAGES
    makes the confidence null and is named (W-CALLS-10); *unmeasured_walk* adds the
    W-CALLS-9 decline for a callee walk beyond depth 1 or --detail; *uncalled* makes it null in every
    language (BACK-2195) and, over a family whose dead-code claims were measured low, names it (W-CALLS-11).
    A census that counted no file has nothing to weight: no confidence, and W-CALLS-12 says so (BACK-2106);
    one that could not be taken says that instead, with its cause (BACK-2248).

    *census* is the per-language file count a caller already holds for this very *path* and scope
    (``CalleeSource.language_census``, BACK-2132); None walks the tree for it. A held census had
    no walk error and kept files, so there is neither a census failure nor a hidden tree to report.
    """
    census_failures: List[PathFailure] = []
    census_unavailable: List[PathFailure] = []

    def _record_census_error(error: OSError) -> None:
        census_failures.append(failure_of(error))

    hidden = HiddenTally()
    per_language = census if census is not None else language_census(
        path, on_error=_record_census_error, on_hidden=hidden,
        on_unavailable=lambda error: census_unavailable.append(failure_of(error)))
    directory_failures = (*traversal_failures, *census_failures)
    total = sum(per_language.values())
    confidence: Optional[float] = None
    if total:
        confidence = round(
            sum(
                calls_extraction_confidence(lang) * count
                for lang, count in per_language.items()
            ) / total,
            4,
        )
        dominant = max(per_language.items(), key=lambda kv: kv[1])[0]
        vocab = CALL_GRAPH_DYNAMIC_DISPATCH_VOCAB.get(dominant, CALL_GRAPH_DEFAULT_DISPATCH_VOCAB)
        implicit_vocab = CALL_GRAPH_IMPLICIT_EXCLUSION_VOCAB.get(
            dominant, CALL_GRAPH_DEFAULT_IMPLICIT_EXCLUSION_VOCAB
        )
    else:
        # Nothing counted (or no census to count by), nothing to weight: _declines adds W-CALLS-12 and the number is withheld.
        dominant = ''
        vocab = CALL_GRAPH_DEFAULT_DISPATCH_VOCAB
        implicit_vocab = CALL_GRAPH_DEFAULT_IMPLICIT_EXCLUSION_VOCAB

    # W-CALLS-2..4 (MRO, importlib, eval/exec) are Python concepts: printed on a
    # C or PHP scan they described a failure mode that does not exist there
    # (BACK-1391). Kept when the language is unknown.
    warnings: List[Any] = list(_CALL_GRAPH_WARNINGS if dominant in ('python', '') else _CALL_GRAPH_WARNINGS[:1])
    warnings[0] = {'code': 'W-CALLS-1', 'message': f'Dynamic dispatch ({vocab}) is not resolved.'}
    warnings.append({'code': 'W-CALLS-7', 'message': (
        'Top-level caller scopes are indexed for Python, JS/TS, PHP and Ruby source files; '
        'module calls retain file/line provenance. Class-body initializers, extensionless Ruby DSL files '
        'and top-level scopes in other languages are outside this relationship scope.')})
    if dominant in ('javascript', 'typescript', 'tsx', ''):
        warnings.append({'code': 'W-CALLS-8', 'message': (
            'JSX component uses are typed jsx_reference relationships; runtime render scheduling is unresolved. '
            'Class-field initializer navigation, string/HTML/Angular templates and Vue/Svelte component relationships are outside this scope.')})
    declines = _declines(per_language, unmeasured_walk, uncalled,
                         census_unavailable[0].cause if census_unavailable else None)
    warnings.extend(declines)
    known_loss = bool(skipped or directory_failures)
    if uncalled:
        heuristic = _UNCALLED_DERIVED_SIGNAL_WARNING
        if known_loss:
            heuristic = {**heuristic, 'message': (
                "'Uncalled' is a derived heuristic, not a separately measured "
                "signal, and the evidence it needs is missing. "
                "Convention-invoked calls (runtime constructors, framework lifecycle hooks, "
                "dynamic dispatch) remain outside static analysis. "
                "Zero callers found is not proof of dead code.")}
        warnings.append(heuristic)
        # BACK-1197: name what was ACTUALLY excluded for the language being
        # scanned, replacing the renderer's old hardcoded Python-only line.
        warnings.append({
            'code': 'W-CALLS-6',
            'message': f'Excludes {implicit_vocab} (implicitly invoked, not statically reachable).',
        })

    # Required analysis loss can leave usable observations alongside missing ones.
    consequence = (
        "analysis is incomplete; missing source or reference evidence can make uncalled "
        "classifications incorrect or incomplete"
        if uncalled else "analysis is incomplete; some callers, callees or uncalled results may be missing")
    failed = analysis_skipped_warning(list(skipped), None, consequence)

    path_obj = Path(path)
    directory = path_obj if path_obj.is_dir() else path_obj.parent
    traversal_warning = traversal_failed_warning(directory_failures, directory)
    # The census walks the tree the index walked: no code file left and something hidden
    # means the empty answer is gitignore's, not the code's (BACK-2065).
    scope_hidden = hidden_entries_warning(hidden, total)
    # Not a loss: what the JS function-value rule left out of the answer, named (BACK-2229).
    left_out = function_values_dropped_warning(dropped)
    warnings.extend(w for w in (failed, traversal_warning, scope_hidden, left_out) if w)

    return {
        'parse_mode': 'tree_sitter_partial' if known_loss else 'tree_sitter_full',
        'confidence': _reported_confidence(confidence, known_loss, declines, uncalled),
        'warnings': warnings,
    }
