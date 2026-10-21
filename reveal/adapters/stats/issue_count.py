"""The issue count that stats://, overview and hotspots print (BACK-1884).

One definition for all three: the count is the findings of the file-local rules only
(``RuleScope.FILE``). A rule that reads other files, a project-wide index or the network
answers differently when a scan cap, a sibling file or the project root changes, so it would
give one file two counts; those rules run under ``reveal check``. The result says so:
``meta.issue_count`` names the counting rule, the rule set (count, stable id and codes) and
any rule that declares no scope, and the text footer repeats it.
"""
import hashlib
from typing import Any, Dict, List, Optional

# The rule registry is imported inside the functions that read it: queries.py takes the
# constants below at import time, and the registry loads every rule module.

COUNTING_RULE = 'file-local rules only'
COUNT_FIELD = 'local_check_issues'

# Field names that were renamed; the old spelling in a filter or ?sort= still works and says so.
DEPRECATED_FIELDS = {'quality.check_issues': f'quality.{COUNT_FIELD}'}
# The penalty key in stats-quality.yaml, renamed the same way.
DEPRECATED_PENALTY_KEY = 'check_issues'


def ignored_codes() -> List[str]:
    """The rules ``check_file`` is told to skip: everything that does not declare FILE."""
    from ...rules import RuleRegistry, RuleScope
    return RuleRegistry.codes_outside_scope(RuleScope.FILE)


def issue_count_basis() -> Dict[str, Any]:
    """What the count counts: the rule, the field, and the rule set with a stable id."""
    from ...rules import RuleRegistry, RuleScope
    codes = RuleRegistry.codes_in_scope(RuleScope.FILE)
    basis: Dict[str, Any] = {
        'rule': COUNTING_RULE,
        'field': COUNT_FIELD,
        'rule_count': len(codes),
        'rule_set_id': hashlib.sha256(','.join(codes).encode('utf-8')).hexdigest()[:8],
        'rules': codes,
    }
    undeclared = RuleRegistry.codes_in_scope(None)
    if undeclared:
        basis['undeclared'] = undeclared
    return basis


def note_issue_count_basis(result: Any) -> None:
    """Record the counting rule in ``result['meta']['issue_count']`` (not on a failed result)."""
    if result.get('error'):
        return
    result.setdefault('meta', {})['issue_count'] = issue_count_basis()


def issue_count_line(result: Any) -> Optional[str]:
    """The one-line text footer for a result that carries ``meta.issue_count``."""
    basis = (result.get('meta') or {}).get('issue_count')
    if not basis:
        return None
    return (f"Issue count ({basis['field']}): {basis['rule']} -- {basis['rule_count']} rules, "
            f"set {basis['rule_set_id']}; cross-file rules run under reveal check")


def renamed_field(field: Optional[str]) -> Optional[str]:
    """The current name of a renamed filter or sort field, or None when it was not renamed."""
    return DEPRECATED_FIELDS.get(field) if field else None
