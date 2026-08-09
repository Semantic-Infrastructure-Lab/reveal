"""Per-rule verified-language coverage (BACK-466 part 1).

The trust question an OSS user has about a `--check` rule is not "does it exist"
but "is it reliable *for my language*?" Reveal now has the data to answer that
honestly: BACK-432's rule-correctness matrix verified all 77 rules (fires when it
should, silent when it shouldn't), organized by applicability class, and
`capabilities.py` records which languages have deep tier-1 conformance ground
truth (the 13-language corpus in `tests/test_conformance_matrix.py`).

This module derives, per rule, the set of languages/formats the rule has been
correctness-verified against — surfaced in `--rules` and `--explain` so a user or
agent sees "verified on Go/Rust/…" vs "best-effort" *before* trusting the output.

Design (BACK-466 part 1):

- **Derived, not hand-maintained.** There is no per-rule `verified_languages`
  table to drift (the exact anti-pattern the goals doc warns against — "machine-
  readable truth needs one home"). The list is computed from the rule's already-
  declared `file_patterns` plus the tier-1 set read live from `capabilities.py`.
  A rule may still override via an explicit class attribute for a genuine
  exception.
- **"Verified" means correctness-verified (BACK-432), capped honestly.** A
  universal rule *applies* to all ~85 languages but was fixture-verified on the 13
  tier-1 families — so that is what it claims. The gap between "applies to" and
  "verified on" is the whole point of the badge.
- **Format rules name their format.** nginx/markdown/Dockerfile rules were
  BACK-432-verified via dedicated per-format suites (independent of their
  analyzer's structural conformance tier), so they claim their format.
"""

from typing import Any, Dict, Iterable, List, Optional, Set

from ..capabilities import (
    CONFORMANCE_TIER1_VERIFIED,
    get_all_capabilities,
    get_capability_for_extension,
)
from ..registry import get_markdown_extensions


def _tier1_languages() -> Set[str]:
    """The languages with deep tier-1 conformance ground truth, read live from
    capabilities.py so this never drifts from the real verification state."""
    return {
        cap.language
        for cap in get_all_capabilities().values()
        if cap.conformance_level == CONFORMANCE_TIER1_VERIFIED
    }


# Format-scoped rule families whose correctness was verified by BACK-432 via
# dedicated per-format suites (test_nginx_rules.py, the markdown/link rule files,
# the Dockerfile S701 tests), independent of their analyzer's structural tier —
# so a `.conf` rule claims "nginx", not the `ini` analyzer's untested tier.
# Detected from tokens in a rule's file_patterns. Markdown's tokens come from
# get_markdown_extensions() at call time, not baked in here — that accessor
# requires analyzers already registered, which isn't guaranteed at import time.
_STATIC_FORMAT_TOKENS = (
    ("nginx", ("nginx", ".nginx", ".conf")),
    ("dockerfile", ("dockerfile",)),
)


def _pattern_format(pattern: str) -> Optional[str]:
    """Map a single file_pattern to a verified *format* label, or None if the
    pattern is an ordinary code-file extension handled via capabilities."""
    p = pattern.lower()
    if any(tok in p for tok in get_markdown_extensions()):
        return "markdown"
    for label, tokens in _STATIC_FORMAT_TOKENS:
        if any(tok in p for tok in tokens):
            return label
    return None


def _pattern_code_language(pattern: str) -> Optional[str]:
    """Resolve a code-file pattern to its analyzer language via capabilities
    (e.g. '.py' -> 'python', '.tsx' -> 'typescript'). Path-glob patterns like
    'reveal/cli/handlers_*.py' resolve on their trailing extension."""
    # Normalize a glob/path to a bare extension the capability map understands.
    ext = pattern
    if "." in pattern:
        ext = "." + pattern.rsplit(".", 1)[-1]
    cap = get_capability_for_extension(ext)
    return cap.language if cap is not None else None


def derive_verified_languages(rule_class: Any) -> List[str]:
    """The languages/formats a rule has been correctness-verified against.

    Returns a sorted list. Universal rules (`file_patterns == ['*']`) claim the
    tier-1-verified language families; language-specific rules claim their own
    language when it is tier-1-verified; format rules claim their format. An
    explicit `verified_languages` class attribute, if set, wins verbatim.
    """
    override = getattr(rule_class, "verified_languages", None)
    if override is not None:
        return sorted(set(override))

    tier1 = _tier1_languages()
    patterns = list(getattr(rule_class, "file_patterns", ["*"]) or ["*"])

    # Universal rules were fixture-verified per major family, not on all ~85
    # languages they nominally apply to — so claim exactly the tier-1 families.
    if patterns == ["*"]:
        return sorted(tier1)

    verified: Set[str] = set()
    for pattern in patterns:
        fmt = _pattern_format(pattern)
        if fmt is not None:
            verified.add(fmt)
            continue
        lang = _pattern_code_language(pattern)
        # Only claim a code language when it carries tier-1 correctness ground
        # truth; smoke-tested/untested analyzers (scala, dart, …) are honestly not
        # yet claimed, even though a broad rule nominally runs on them.
        if lang is not None and lang in tier1:
            verified.add(lang)
    return sorted(verified)


def _rule_targets_code(rule_class: Any) -> bool:
    """Whether *rule_class* is scoped to source-code languages at all, as
    opposed to a doc/config format (nginx, Dockerfile, markdown) — those
    rules never claim a code language regardless of how well-verified they
    are, so they would otherwise show up as a false gap for every language.
    """
    patterns = list(getattr(rule_class, "file_patterns", ["*"]) or ["*"])
    if patterns == ["*"]:
        return True
    for pattern in patterns:
        # A format pattern (Dockerfile, nginx .conf) can still resolve to a
        # registered analyzer/language under the hood (e.g. "Dockerfile" has
        # its own capability entry) — check format first, same precedence
        # derive_verified_languages uses, so it isn't double-counted as code.
        if _pattern_format(pattern) is not None:
            continue
        if _pattern_code_language(pattern) is not None:
            return True
    return False


def _category_value(rule_class: Any) -> str:
    category = getattr(rule_class, "category", None)
    if not category:
        return "unknown"
    return category if isinstance(category, str) else category.value


def unscoped_rule_categories(
    languages: Iterable[str], rule_classes: List[Any]
) -> List[Dict[str, Any]]:
    """BACK-1021: which (language, rule-category) pairs among *rule_classes*
    have zero verified coverage for a language actually present in *languages*.

    A `check` run reporting "0 issues" is otherwise indistinguishable between
    "genuinely clean" and "this category has never been correctness-verified
    on this language" — this is the signal that tells the two apart. Doc/config
    -format rules (nginx, Dockerfile, markdown) are excluded via
    `_rule_targets_code` since they never claim a code language and would
    otherwise flag as a gap for every language, every time.

    Returns one dict per gap: `{"language": ..., "category": ...}`. Empty when
    every present language has at least one verified rule per active
    code-targeting category — the common (fully-scoped) case.
    """
    code_rules = [r for r in rule_classes if _rule_targets_code(r)]
    coverage: Dict[str, Set[str]] = {}
    for rule_class in code_rules:
        cat = _category_value(rule_class)
        coverage.setdefault(cat, set()).update(derive_verified_languages(rule_class))

    gaps = []
    for lang in sorted(set(languages)):
        for cat in sorted(coverage):
            if lang not in coverage[cat]:
                gaps.append({"language": lang, "category": cat})
    return gaps
