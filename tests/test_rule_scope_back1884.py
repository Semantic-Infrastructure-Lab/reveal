"""BACK-1884: every rule declares what it reads (RuleScope), and the registry answers from it.

The issue count that stats://, overview and hotspots print counts the FILE rules only. The set
is not a hand-typed code list: it is whatever the rules declare, so a rule that does not declare
a scope fails here, and a rule that reads other files cannot slip into the count unnoticed.
"""
import inspect
import re

import pytest

from reveal.rules import RuleRegistry
from reveal.rules.base import BaseRule, RulePrefix, RuleScope, Severity
from reveal.rules.scan_caches import preload_scan_caches

pytestmark = pytest.mark.component


def _builtin_rules():
    RuleRegistry.discover()
    return [r for r in RuleRegistry._rules if r.__module__.startswith('reveal.rules.')]


def test_every_builtin_rule_declares_a_scope():
    """A new rule has to say what it reads: None (the BaseRule default) fails here."""
    rules = _builtin_rules()
    assert len(rules) >= 90, f'rule discovery found only {len(rules)} built-in rules'
    undeclared = sorted(r.code for r in rules if not isinstance(r.scope, RuleScope))
    assert not undeclared, f'rules without a declared RuleScope: {undeclared}'


# One rule of each kind, chosen independently of the declarations: the reason is what the
# rule's own check() reads. The nginx/layer/tree-validation rows are classifications that
# differ from the BACK-1884 memo's local_codes.txt (BACK-2127), each with its evidence.
EXPECTED = {
    'B001': RuleScope.FILE,           # bare except: the file's own syntax tree
    'C901': RuleScope.FILE,           # complexity of this file's functions
    'E501': RuleScope.FILE,           # line length
    'I001': RuleScope.FILE,           # unused imports, from this file's structure
    'I005': RuleScope.FILE,           # duplicate imports; re-extracts imports of this same file
    'D002': RuleScope.FILE,           # duplicate functions within one file (opt-in, disabled)
    'S701': RuleScope.FILE,           # security pattern in this file
    'V016': RuleScope.FILE,           # adapter file missing get_help(): file mode reads the file
    'D005': RuleScope.PROJECT_INDEX,  # literal index over the whole project
    'I002': RuleScope.PROJECT_INDEX,  # import graph of the whole project
    'I007': RuleScope.PROJECT_INDEX,  # declared-dependency inventory
    'M102': RuleScope.PROJECT_INDEX,  # who imports what, project-wide
    'T006': RuleScope.PROJECT_INDEX,  # TypedDict index
    'B005': RuleScope.CROSS_FILE,     # resolves relative imports against sibling files
    'I003': RuleScope.CROSS_FILE,     # resolves each import to a path on disk (layer check)
    'I004': RuleScope.CROSS_FILE,     # looks for __init__.py in parent directories
    'L001': RuleScope.CROSS_FILE,     # link targets and anchors in other files
    'L002': RuleScope.CROSS_FILE,     # network (opt-in, disabled)
    'U502': RuleScope.CROSS_FILE,     # reads pyproject.toml
    'N002': RuleScope.CROSS_FILE,     # follows nginx include files
    'N007': RuleScope.CROSS_FILE,     # opens the ssl_certificate file the config names
    'N010': RuleScope.CROSS_FILE,     # reads include snippets and reports in them
    'V001': RuleScope.CROSS_FILE,     # reveal:// self-check only
    'V041': RuleScope.CROSS_FILE,     # scans reveal's source tree; answers [] for a file
}


@pytest.mark.parametrize('code, scope', sorted(EXPECTED.items()))
def test_classification_matches_independent_expectation(code, scope):
    RuleRegistry.discover()
    assert RuleRegistry.get_rule(code).scope == scope


def test_project_index_rules_are_exactly_the_shared_index_preloads(tmp_path):
    """scan_caches.py already names the rules that build a project-wide index (it preloads
    them for pool workers); the declarations must agree with it, in both directions."""
    RuleRegistry.discover()
    preloaded = set(preload_scan_caches([], tmp_path, None, None))
    declared = {r.code for r in _builtin_rules() if r.scope == RuleScope.PROJECT_INDEX}
    assert declared == preloaded


# A rule declared FILE must not walk or list the filesystem. V016 walks adapters/ with rglob
# only in its reveal:// self-check branch (its file mode reads the one file).
_WALKS = re.compile(r'\.rglob\(|\.glob\(|os\.walk\(|os\.scandir\(|os\.listdir\(|\.iterdir\(')
_WALK_IN_URI_MODE = {'V016'}


def test_no_file_rule_walks_the_filesystem():
    offenders = []
    for rule in _builtin_rules():
        if rule.scope != RuleScope.FILE or rule.code in _WALK_IN_URI_MODE:
            continue
        source = inspect.getsource(inspect.getmodule(rule))
        if _WALKS.search(source):
            offenders.append(rule.code)
    assert not offenders, f'FILE rules whose module walks the filesystem: {offenders}'


def test_codes_in_and_outside_scope_partition_the_registry():
    RuleRegistry.discover()
    inside = set(RuleRegistry.codes_in_scope(RuleScope.FILE))
    outside = set(RuleRegistry.codes_outside_scope(RuleScope.FILE))
    assert not inside & outside
    assert {'B001', 'C901'} <= inside and {'I002', 'L001', 'V001'} <= outside
    assert 'D002' not in inside, 'a disabled rule is not in the counted set'
    assert 'D002' not in outside, 'but it is declared FILE'
    assert inside | outside | {'D002'} >= {r.code for r in _builtin_rules() if r.enabled}


class _Undeclared(BaseRule):
    code = 'X8841'
    message = 'plugin rule that declares no scope'
    category = RulePrefix.B
    severity = Severity.LOW
    file_patterns = ['*']


class _StringScope(_Undeclared):
    code = 'X8842'
    scope = 'file'   # a plugin may write the string, as it may for severity


def test_undeclared_scope_is_outside_every_scope_and_a_string_scope_counts(monkeypatch):
    RuleRegistry.discover()
    monkeypatch.setattr(RuleRegistry, '_rules', [*RuleRegistry._rules, _Undeclared, _StringScope])
    assert 'X8841' in RuleRegistry.codes_outside_scope(RuleScope.FILE)
    assert 'X8841' not in RuleRegistry.codes_in_scope(RuleScope.FILE)
    assert 'X8842' in RuleRegistry.codes_in_scope(RuleScope.FILE)
    assert 'X8842' not in RuleRegistry.codes_outside_scope(RuleScope.FILE)
