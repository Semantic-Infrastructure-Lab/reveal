"""A custom schema rule without field/check must be reported, not skipped (BACK-2213 C17)."""
from unittest.mock import patch

from reveal.rules.frontmatter.F005 import F005

STRUCTURE = {'frontmatter': {'data': {'title': 'x'}, 'line_start': 1}}


def _run(rules):
    schema = {'name': 'custom', 'validation_rules': rules}
    with patch('reveal.rules.frontmatter.F005.get_validation_schema', return_value=schema):
        return F005().check('doc.md', STRUCTURE, '')


def test_rule_without_field_and_check_is_reported():
    found = _run([{'name': 'n', 'expression': "len(title) > 3", 'message': 'm'}])
    assert len(found) == 1
    assert "'field'" in found[0].message and "'check'" in found[0].message


def test_well_formed_rule_still_passes_silently():
    assert _run([{'field': 'title', 'check': 'len(value) > 0', 'message': 'm'}]) == []
