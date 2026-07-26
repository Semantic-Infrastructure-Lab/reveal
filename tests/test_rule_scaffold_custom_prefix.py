"""BACK-855 — rules scaffolded with a prefix outside the known RulePrefix set.

`cli/scaffold/rule.py:_get_category_value` deliberately stores a plain string
in `category` (e.g. "Z") instead of a `RulePrefix` member when the rule code's
prefix isn't one of the ten known ones (B/C/D/E/F/I/M/N/S/V) — see its
docstring. Several consumers of `rule_class.category` assumed it was always
either falsy or a `RulePrefix` enum and called `.value` on it unconditionally,
crashing `reveal --rules` (RuleRegistry._rule_to_dict) and
`reveal --explain <code>` (handle_explain_rule) for the *entire* rule listing
the moment one such rule was discovered — not just failing to describe the
one odd rule.
"""

import pytest
from unittest.mock import patch

from reveal.rules import RuleRegistry, BaseRule, Severity


class _CustomPrefixRule(BaseRule):
    code = "Z999"
    message = "zzz-pattern"
    category = "Z"  # plain string, as the scaffold emits for unknown prefixes
    severity = Severity.MEDIUM
    file_patterns = ["*"]
    version = "1.0.0"

    def check(self, file_path, structure, content):
        return []


def test_rule_to_dict_handles_string_category():
    result = RuleRegistry._rule_to_dict(_CustomPrefixRule)
    assert result["category"] == "Z"


def test_explain_rule_handles_string_category(capsys):
    from reveal.cli.handlers.introspection import handle_explain_rule

    with patch.object(RuleRegistry, "get_rule", return_value=_CustomPrefixRule):
        with pytest.raises(SystemExit):
            handle_explain_rule("Z999")

    out = capsys.readouterr().out
    assert "Category: Z" in out
