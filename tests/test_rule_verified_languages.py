"""BACK-466 part 1 — per-rule verified-language coverage.

`derive_verified_languages` answers "is this rule reliable for my language?" from
data that already exists: the rule's `file_patterns` plus the tier-1 conformance
set in `capabilities.py`. These tests pin the properties that make the badge
*trustworthy* rather than decorative:

- **Honest**: a rule never claims a language it wasn't correctness-verified on —
  universal rules claim exactly the tier-1 families (not all ~85 they run on),
  and language-specific rules claim only their own tier-1 language.
- **Non-drifting**: the tier-1 basis is read live from capabilities, so when a
  language is promoted/demoted there, every universal rule's badge moves with it
  — there is no hand-maintained per-rule table to rot.
- **Populated**: every public rule resolves to a non-empty set, so the badge is
  informative for the whole surface (the precondition BACK-432's 77/77 unlocked).
- **Overridable**: an explicit `verified_languages` class attribute wins, for the
  rare rule the derivation would get wrong.
"""

import pytest

from reveal.rules import RuleRegistry
from reveal.rules.coverage import (
    derive_verified_languages,
    unscoped_rule_categories,
    _tier1_languages,
)

# BACK-1149: cross-language conformance/smoke coverage
pytestmark = pytest.mark.conformance


# --------------------------------------------------------------------------- #
# Per applicability-class derivation
# --------------------------------------------------------------------------- #

def _rule(code):
    RuleRegistry.discover()
    r = RuleRegistry.get_rule(code)
    assert r is not None, f"rule {code} not found"
    return r


def test_universal_rule_claims_exactly_the_tier1_families():
    """A `file_patterns=['*']` rule runs on every language but was fixture-
    verified only on the tier-1 families — it must claim those, no more."""
    verified = derive_verified_languages(_rule("C901"))  # complexity, universal
    assert set(verified) == _tier1_languages(), (
        f"universal rule claims {verified}, expected the tier-1 set "
        f"{sorted(_tier1_languages())}"
    )


def test_python_only_rule_claims_only_python():
    # B002 (@staticmethod+self) has no non-Python analog (BACK-1011 note #1) —
    # unlike B001, it stays ['.py'] permanently, making it the stable example.
    verified = derive_verified_languages(_rule("B002"))  # ['.py']
    assert verified == ["python"], f"python-only rule claims {verified}"


def test_multi_language_rule_claims_all_its_verified_languages():
    # B001 (bare/untyped except-all) was ported to C#/C++ (BACK-1011) — its
    # file_patterns now span three tier-1-verified languages, all claimed.
    verified = derive_verified_languages(_rule("B001"))
    assert verified == ["cpp", "csharp", "python"], f"B001 claims {verified}"


def test_nginx_rule_claims_nginx_not_its_ini_analyzer_tier():
    """`.conf` rules resolve through the `ini` analyzer (untested tier), but the
    *rule* was BACK-432-verified on nginx configs — so it claims nginx."""
    verified = derive_verified_languages(_rule("N001"))
    assert verified == ["nginx"], f"nginx rule claims {verified}"


def test_markdown_rule_claims_markdown():
    verified = derive_verified_languages(_rule("F001"))  # ['.md', '.markdown']
    assert verified == ["markdown"], f"markdown rule claims {verified}"


def test_dockerfile_rule_claims_dockerfile():
    verified = derive_verified_languages(_rule("S701"))
    assert verified == ["dockerfile"], f"dockerfile rule claims {verified}"


# --------------------------------------------------------------------------- #
# Honesty & non-drift invariants across the whole public surface
# --------------------------------------------------------------------------- #

def _public_rules():
    RuleRegistry.discover()
    return [r for r in RuleRegistry._rules if not r.internal]


def test_every_public_rule_has_a_populated_badge():
    """The badge must be informative for the entire public surface — an empty
    list reads as 'unverified' and would undersell BACK-432's completed matrix."""
    empty = [r.code for r in _public_rules() if not derive_verified_languages(r)]
    assert not empty, f"public rules with no verified languages: {empty}"


def test_no_rule_claims_an_unverified_code_language():
    """Honesty guard: the only code languages a rule may claim are tier-1-
    verified ones. Formats (nginx/markdown/dockerfile) are the allowed non-code
    labels. A smoke-tested language (scala, dart) must never appear as 'verified'."""
    tier1 = _tier1_languages()
    allowed_formats = {"nginx", "markdown", "dockerfile"}
    for r in _public_rules():
        for claimed in derive_verified_languages(r):
            assert claimed in tier1 or claimed in allowed_formats, (
                f"rule {r.code} claims {claimed!r}, which is neither tier-1-"
                f"verified nor a known verified format"
            )


def test_badge_tracks_capabilities_live_not_a_frozen_copy():
    """The universal-rule badge is the tier-1 set by derivation, so it can't
    drift from capabilities.py — assert they are the same object of truth."""
    universal = set(derive_verified_languages(_rule("C902")))
    assert universal == _tier1_languages()


# --------------------------------------------------------------------------- #
# Override & registry integration
# --------------------------------------------------------------------------- #

def test_explicit_override_wins_verbatim():
    class _Fake:
        file_patterns = ["*"]
        verified_languages = ["python", "go"]
    assert derive_verified_languages(_Fake) == ["go", "python"]


def test_list_rules_dict_exposes_verified_languages():
    """The programmatic contract agents consume (`RuleRegistry.list_rules`) must
    carry the field, not just the human `--rules` text."""
    rules = RuleRegistry.list_rules(include_internal=False)
    assert rules, "no public rules discovered"
    for r in rules:
        assert "verified_languages" in r, f"{r['code']} dict missing verified_languages"
        assert isinstance(r["verified_languages"], list)


# --------------------------------------------------------------------------- #
# BACK-1021 — unscoped_rule_categories: the silent-clean vs unscoped signal
# --------------------------------------------------------------------------- #

def _fake_rule(category, patterns=("*",), verified=None):
    class _Fake:
        file_patterns = list(patterns)
    _Fake.category = category
    if verified is not None:
        _Fake.verified_languages = verified
    return _Fake


def test_no_gap_when_every_present_language_is_covered():
    rules = [_fake_rule("B", verified=["python", "go"])]
    gaps = unscoped_rule_categories(["python", "go"], rules)
    assert gaps == []


def test_flags_language_with_zero_verified_rules_in_a_present_category():
    rules = [_fake_rule("B", verified=["python"])]
    gaps = unscoped_rule_categories(["python", "go"], rules)
    assert gaps == [{"language": "go", "category": "B"}]


def test_flags_per_category_independently():
    rules = [
        _fake_rule("B", verified=["python"]),
        _fake_rule("D", verified=["python", "go"]),
    ]
    gaps = unscoped_rule_categories(["python", "go"], rules)
    assert gaps == [{"language": "go", "category": "B"}]


def test_format_only_rules_never_produce_a_code_language_gap():
    """A Dockerfile/nginx-only rule should not be reported as 'unscoped for go'
    — it was never meant to apply to arbitrary code languages, so flagging it
    would be pure noise, not a real trust gap."""
    rules = [_fake_rule("I", patterns=["Dockerfile"], verified=["dockerfile"])]
    gaps = unscoped_rule_categories(["python", "go"], rules)
    assert gaps == []


def test_category_absent_from_active_rules_produces_no_gap():
    """Only categories among the *currently active* rules (post --select/--ignore
    filtering) are considered — a category nobody asked to run this time must
    not show up as a false gap."""
    rules = [_fake_rule("B", verified=["python"])]
    gaps = unscoped_rule_categories(["python", "go", "rust"], rules)
    assert all(g["category"] == "B" for g in gaps)
    assert {g["language"] for g in gaps} == {"go", "rust"}


def test_real_universal_rule_flags_a_non_tier1_language_but_not_python():
    """Integration check against the live registry: a real universal rule
    (verified on exactly the tier-1 set) must produce a gap for a genuinely
    unverified language and none for python."""
    RuleRegistry.discover()
    rules = [RuleRegistry.get_rule("C901")]
    tier1 = _tier1_languages()
    non_tier1 = next(lang for lang in ("cobol", "prolog", "fortran") if lang not in tier1)
    gaps = unscoped_rule_categories(["python", non_tier1], rules)
    assert {"language": "python", "category": "C"} not in gaps
    assert {"language": non_tier1, "category": "C"} in gaps
