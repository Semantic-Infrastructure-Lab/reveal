"""BACK-1063: assert every reveal.defaults.RuleDefaults value matches the
hardcoded constant actually used by its documented rule.

RuleDefaults exists to be the single documented source of truth for rule
thresholds, but nothing wires rules to read from it -- each rule keeps its
own duplicate constant instead. That already drifted silently once (B003:
declared 8, hardcoded 15, fixed this session) and was caught happening again
mid-fix for a second rule (C902's warn tier: declared 50, hardcoded 75 --
BACK-1050, a separate ticket, not fixed here). This test is the ratchet: it
fails the moment a rule's hardcoded value stops matching what defaults.py
documents, instead of the drift sitting undetected for weeks.
"""
import pytest

from reveal.defaults import RuleDefaults
from reveal.rules.bugs.B003 import B003
from reveal.rules.complexity.C901 import C901
from reveal.rules.complexity.C902 import C902
from reveal.rules.complexity.C905 import C905
from reveal.rules.duplicates.D002 import D002
from reveal.rules.errors.E501 import E501
from reveal.rules.links.L002 import L002
from reveal.rules.links.L005 import L005
from reveal.rules.maintainability.M101 import M101
from reveal.rules.maintainability.M104 import M104
from reveal.rules.refactoring.R913 import R913

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component

# (rule_class, rule_attr, defaults_attr, xfail_reason)
# xfail_reason is None for pairs that are currently consistent; set it to
# document a KNOWN, already-filed drift rather than silently exempting it.
CASES = [
    (C901, "DEFAULT_THRESHOLD", "CYCLOMATIC_COMPLEXITY", None),
    (C905, "MAX_DEPTH", "NESTING_DEPTH_MAX", None),
    (
        C902, "THRESHOLD_WARN", "FUNCTION_LENGTH_WARN",
        "BACK-1050: C902 warn tier hardcodes 75, defaults.py declares 50 -- "
        "confirmed drift, fix is a separate ticket (changes rule-firing "
        "behavior, not just a constant).",
    ),
    (C902, "THRESHOLD_ERROR", "FUNCTION_LENGTH_ERROR", None),
    (M101, "THRESHOLD_WARN", "FILE_LENGTH_WARN", None),
    (M101, "THRESHOLD_ERROR", "FILE_LENGTH_ERROR", None),
    (E501, "DEFAULT_MAX_LENGTH", "MAX_LINE_LENGTH", None),
    (R913, "MAX_ARGS", "MAX_FUNCTION_ARGUMENTS", None),
    (B003, "MAX_PROPERTY_LINES", "MAX_PROPERTY_LINES", None),
    (D002, "MIN_FUNCTION_SIZE", "MIN_FUNCTION_SIZE", None),
    (D002, "MIN_SIMILARITY", "MIN_SIMILARITY", None),
    (D002, "MAX_CANDIDATES", "MAX_DUPLICATE_CANDIDATES", None),
    (M104, "MIN_LIST_SIZE", "MIN_LIST_SIZE", None),
    (M104, "MIN_DICT_VALUE_SIZE", "MIN_DICT_VALUE_SIZE", None),
    (L002, "TIMEOUT", "LINK_TIMEOUT", None),
    (L005, "MIN_CROSS_REFS", "MIN_CROSS_REFS", None),
]


def _case_id(case):
    rule_class, rule_attr, defaults_attr, _ = case
    return f"{rule_class.__name__}.{rule_attr}=={defaults_attr}"


@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_rule_constant_matches_declared_default(case):
    rule_class, rule_attr, defaults_attr, xfail_reason = case
    if xfail_reason:
        pytest.xfail(xfail_reason)
    rule_value = getattr(rule_class, rule_attr)
    default_value = getattr(RuleDefaults, defaults_attr)
    assert rule_value == default_value, (
        f"{rule_class.__name__}.{rule_attr} = {rule_value!r} but "
        f"RuleDefaults.{defaults_attr} = {default_value!r} -- either the "
        f"rule drifted from its declared default, or defaults.py is stale. "
        f"Whichever is correct, fix the other one to match."
    )


def test_all_ruledefaults_constants_are_covered():
    """Every RuleDefaults constant should appear in CASES above at least
    once -- catches a new threshold being added to defaults.py without a
    matching consistency case (the same blind spot that let B003/C902 drift
    unnoticed in the first place)."""
    declared = {
        name for name in vars(RuleDefaults)
        if not name.startswith("_") and name.isupper()
    }
    covered = {defaults_attr for _, _, defaults_attr, _ in CASES}
    missing = declared - covered
    assert not missing, (
        f"RuleDefaults constants with no consistency check: {sorted(missing)} "
        f"-- add a CASES entry in this file for each."
    )
