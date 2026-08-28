"""Shared per-(language, adapter, signal) capability/confidence registry (BACK-1093).

BACK-1093's finding: `depends://`'s honest-decline invariant (True/False/None
intra-project classification, BACK-547) and `calls://`'s per-language
extraction-confidence table (BACK-1198) are two independently hand-built
trust mechanisms with zero shared surface — an adapter or rule that wants to
know "how much should I trust this signal for language X" has to know which
of two unrelated, adapter-private mechanisms to consult, and any THIRD
adapter that needs the same kind of answer would have to invent a third one.
This module is the one place either question is asked from now on.

The two signals are genuinely different in kind, not just in owner, so this
is not a single flat lookup table:

- `calls_extraction_confidence()` is a MEASURED float (recall against real
  oracle corpora, see `defaults.CALL_GRAPH_EXTRACTION_CONFIDENCE`'s
  docstring) — necessarily hand-maintained, since no amount of static
  analysis of reveal's own code tells you how well tree-sitter's grammar for
  a language actually resolves calls in real code.
- `depends_intra_project_classification_supported()` is a DERIVED boolean —
  whether a language's import extractor can ever return real True/False
  from `is_intra_project_import()`, as opposed to always falling through to
  the conservative (honest, but uninformative) `None`. This one is computed
  once from each registered extractor's own declared behavior (spec flags /
  method override), not hand-maintained, so it can't silently drift from the
  code the way a hardcoded language list could.

Both are exposed here under one import so a caller doesn't need to know
which adapter originally owned the answer.
"""

from typing import Dict, Optional

from .imports.base import LanguageExtractor, _EXTRACTOR_REGISTRY
from .imports.generic import _GenericTreeSitterImportExtractor
from ..defaults import CALL_GRAPH_EXTRACTION_CONFIDENCE, CALL_GRAPH_DEFAULT_CONFIDENCE


def calls_extraction_confidence(language: str) -> float:
    """calls://'s per-language call-graph extraction-recall confidence
    (BACK-1198). Delegates to `defaults.CALL_GRAPH_EXTRACTION_CONFIDENCE`
    unchanged — this function exists so callers outside calls:// (other
    adapters, rules) consult the same measured figures through one shared
    surface instead of importing that adapter-owned constant directly.
    """
    return CALL_GRAPH_EXTRACTION_CONFIDENCE.get(language, CALL_GRAPH_DEFAULT_CONFIDENCE)


def _extractor_has_real_classification(extractor_cls: type) -> bool:
    """True if *extractor_cls* can return real True/False from
    `is_intra_project_import()` for at least one import shape, rather than
    always falling through to the base class's honest-but-uninformative
    `None` default.

    A dedicated per-language override (python.py/go.py/javascript.py)
    always counts. The shared generic implementation
    (`_GenericTreeSitterImportExtractor`, used by C/C++/Java/C#/PHP/Ruby/
    Swift/Kotlin/Scala/Dart/GDScript/Lua) only counts when the extractor's
    own `_ImportSpec` sets one of the flags that implementation's
    `is_intra_project_import()` actually branches on — merely using that
    shared class is not itself a capability, since several of its spec
    combinations still fall through to `None` (e.g. a language with no
    include/namespace/module-directory convention at all).
    """
    override = extractor_cls.is_intra_project_import
    if override is LanguageExtractor.is_intra_project_import:
        return False
    if override is _GenericTreeSitterImportExtractor.is_intra_project_import:
        spec = getattr(extractor_cls, 'spec', None)
        return bool(spec is not None and (
            spec.resolve_includes
            or spec.resolve_namespaces
            or spec.package_node_types
            or spec.module_dir_convention
        ))
    return True


_intra_project_classification_support: Optional[Dict[str, bool]] = None


def _build_intra_project_classification_support() -> Dict[str, bool]:
    support: Dict[str, bool] = {}
    seen: set = set()
    for extractor_cls in _EXTRACTOR_REGISTRY.values():
        if extractor_cls in seen:
            continue
        seen.add(extractor_cls)
        support[extractor_cls.language_name] = _extractor_has_real_classification(extractor_cls)
    return support


def depends_intra_project_classification_supported(language_name: str) -> bool:
    """True if `depends://`'s honest-decline classifier (BACK-547) produces
    a real True/False signal for *language_name*, rather than always
    falling through to the conservative `None` default (no signal at all
    for this language — every unresolved import from it is silently
    excluded from `_unresolved_intra`, so `confidence: 'high'` on a scan
    dominated by this language does not mean what it looks like it means).

    Computed once (cached module-level) from the registered extractors'
    own declared behavior — see `_extractor_has_real_classification()`.
    *language_name* is the `LanguageExtractor.language_name` string (e.g.
    ``'Python'``, ``'Swift'``), not a file extension.
    """
    global _intra_project_classification_support
    if _intra_project_classification_support is None:
        _intra_project_classification_support = _build_intra_project_classification_support()
    return _intra_project_classification_support.get(language_name, False)
