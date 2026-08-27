"""calls:// meta (confidence/warnings) computation — BACK-1198.

Previously calls:// emitted a single hardcoded ``confidence: 0.85`` and a
Python-vocabulary "dynamic dispatch" warning, unconditionally, regardless of
the language(s) being scanned — identical output for a language reveal has
measured at 100% call-graph extraction recall and one with real, documented
residual gaps. Split into its own module (out of adapter.py) once it grew
past a few constants, to keep adapter.py under reveal's own file-length gate.

See ``defaults.CALL_GRAPH_EXTRACTION_CONFIDENCE`` for where the per-language
numbers come from (reveal's own VALIDATION.md oracle recall figures).
"""

from pathlib import Path
from typing import Any, Dict

from ...defaults import (
    CALL_GRAPH_EXTRACTION_CONFIDENCE,
    CALL_GRAPH_DEFAULT_CONFIDENCE,
    CALL_GRAPH_DYNAMIC_DISPATCH_VOCAB,
    CALL_GRAPH_DEFAULT_DISPATCH_VOCAB,
)
from ...utils.path_utils import census_for_path

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
# is not itself a measured signal; it's DERIVED from the (measured)
# extraction confidence plus every convention-invoked call no static tool
# sees (constructors invoked by the language runtime, e.g. Ruby's `.new` ->
# `initialize`; framework lifecycle hooks; dynamic dispatch). Reporting one
# confidence number for both extraction accuracy and "is this really dead
# code" was the actual modelling error this ticket found.
_UNCALLED_DERIVED_SIGNAL_WARNING = {
    'code': 'W-CALLS-5',
    'message': (
        "'Uncalled' is a derived heuristic, not a separately measured "
        "signal -- it inherits the confidence above PLUS every "
        "convention-invoked call static analysis cannot see (runtime "
        "constructors, framework lifecycle hooks, dynamic dispatch). "
        "Zero callers found is not proof of dead code."
    ),
}


def language_census(path: str) -> Dict[str, int]:
    """Per-language file counts under *path* (BACK-1198) — single walk,
    shared by the confidence and dynamic-dispatch-vocabulary computation.
    Empty dict (not an exception) on a missing/unreadable path — callers
    fall back to the language-agnostic defaults, same as the "unmeasured
    language" case.
    """
    try:
        return dict(census_for_path(Path(path)).per_language)
    except OSError:
        return {}


def build_meta(path: str, *, uncalled: bool = False) -> Dict[str, Any]:
    """Per-request calls:// meta kwargs (BACK-1198).

    Replaces the prior flat ``confidence: 0.85`` (identical for a language
    measured at 100% extraction recall and one with real residual gaps) with
    a file-count-weighted average of the per-language figures reveal has
    actually measured (``defaults.CALL_GRAPH_EXTRACTION_CONFIDENCE``), and
    swaps the generic "dynamic dispatch... getattr..." warning (Python
    vocabulary, printed unconditionally on every language) for the dominant
    language's own dispatch idioms.
    """
    per_language = language_census(path)
    total = sum(per_language.values())
    if total:
        confidence = round(
            sum(
                CALL_GRAPH_EXTRACTION_CONFIDENCE.get(lang, CALL_GRAPH_DEFAULT_CONFIDENCE) * count
                for lang, count in per_language.items()
            ) / total,
            4,
        )
        dominant = max(per_language.items(), key=lambda kv: kv[1])[0]
        vocab = CALL_GRAPH_DYNAMIC_DISPATCH_VOCAB.get(dominant, CALL_GRAPH_DEFAULT_DISPATCH_VOCAB)
    else:
        confidence = CALL_GRAPH_DEFAULT_CONFIDENCE
        vocab = CALL_GRAPH_DEFAULT_DISPATCH_VOCAB

    warnings = list(_CALL_GRAPH_WARNINGS)
    warnings[0] = {'code': 'W-CALLS-1', 'message': f'Dynamic dispatch ({vocab}) is not resolved.'}
    if uncalled:
        warnings.append(_UNCALLED_DERIVED_SIGNAL_WARNING)

    return {
        'parse_mode': 'tree_sitter_full',
        'confidence': confidence,
        'warnings': warnings,
    }
