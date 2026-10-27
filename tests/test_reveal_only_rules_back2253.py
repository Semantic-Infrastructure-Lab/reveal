"""BACK-2253: a rule that judges reveal's own source as a whole runs on a reveal:// target only.

`reveal check reveal` handed V017 one file at a time. V017 compares core/node_taxonomy.py with
treesitter.py, so on either file (or the back-compat shim at adapters/ast/node_taxonomy.py) it
reported "0 function node types found" for a file it was never meant to judge alone, while
`reveal reveal:// --check` was clean. `internal` only hid such rules from listings; nothing stopped
the registry from matching them against a real path. The registry now does, for every internal rule
that is not FILE scope. A FILE-scope internal rule (B007) reads only the file it is handed, so a
per-file check of reveal's tree stays legitimate for it.
"""
from pathlib import Path

import pytest

import reveal
from reveal.rules import RuleRegistry
from reveal.rules.base import BaseRule, RulePrefix, RuleScope, Severity

pytestmark = pytest.mark.component

_REVEAL_ROOT = Path(reveal.__file__).resolve().parent
_TAXONOMY_FILES = (
    _REVEAL_ROOT / 'core' / 'node_taxonomy.py',
    _REVEAL_ROOT / 'adapters' / 'ast' / 'node_taxonomy.py',
    _REVEAL_ROOT / 'treesitter.py',
)
_REAL_PATHS = (*map(str, _TAXONOMY_FILES), 'src/x.py', 'docs/README.md', '/abs/dir/notes.md')
_REVEAL_URIS = ('reveal://', 'reveal://treesitter.py', 'reveal://docs/GUIDE.md')


def _builtin_rules():
    RuleRegistry.discover()
    return [r for r in RuleRegistry._rules if r.__module__.startswith('reveal.rules.')]


def _reveal_only_rules():
    return [r for r in _builtin_rules() if r.internal and r.scope != RuleScope.FILE]


def test_the_reveal_only_set_is_the_internal_rules_that_read_other_files():
    codes = {r.code for r in _reveal_only_rules()}
    assert {'V001', 'V009', 'V017', 'V026', 'V042'} <= codes
    assert len(codes) >= 30, f'only {sorted(codes)}'
    assert 'B007' not in codes, 'an internal FILE rule reads only its own file'
    assert 'I002' not in codes, 'a public cross-file rule is meant for user projects'


@pytest.mark.parametrize('rule', sorted(_reveal_only_rules(), key=lambda r: r.code), ids=lambda r: r.code)
def test_a_reveal_only_rule_does_not_match_a_filesystem_path(rule):
    matched = [p for p in _REAL_PATHS if rule.matches_target(p)]
    assert not matched, f'{rule.code} is matched against real paths: {matched}'


@pytest.mark.parametrize('rule', sorted(_reveal_only_rules(), key=lambda r: r.code), ids=lambda r: r.code)
def test_a_reveal_only_rule_still_matches_a_reveal_uri(rule):
    assert any(rule.matches_target(uri) for uri in _REVEAL_URIS), f'{rule.code} can no longer run'


class _Base(BaseRule):
    code = 'X8851'
    message = 'synthetic'
    category = RulePrefix.V
    severity = Severity.LOW
    file_patterns = ['.py']
    uri_patterns = ['^reveal://.*']


class _InternalCrossFile(_Base):
    scope = RuleScope.CROSS_FILE
    internal = True


class _InternalCrossFileText(_Base):
    scope = 'cross_file'   # a plugin may write the string, as it may for severity
    internal = True


class _InternalFile(_Base):
    scope = RuleScope.FILE
    internal = True


class _PublicCrossFile(_Base):
    scope = RuleScope.CROSS_FILE


class _Undeclared(_Base):
    internal = True


@pytest.mark.parametrize('rule', [_InternalCrossFile, _InternalCrossFileText])
def test_internal_cross_file_rule_matches_only_a_reveal_uri(rule):
    assert not rule.matches_target('pkg/mod.py')
    assert not rule.matches_target(Path('pkg/mod.py'))
    assert rule.matches_target('reveal://')
    assert rule.matches_target('reveal://pkg/mod.py')


@pytest.mark.parametrize('rule', [_InternalFile, _PublicCrossFile, _Undeclared])
def test_other_rules_still_match_a_real_file(rule):
    """Positive controls: the gate is the pair internal + not FILE, not either alone."""
    assert rule.matches_target('pkg/mod.py')
    assert not rule.matches_target('pkg/mod.txt')


@pytest.mark.parametrize('path', _TAXONOMY_FILES, ids=lambda p: '/'.join(p.parts[-3:]))
def test_v017_is_skipped_not_misjudged_on_a_taxonomy_file(path):
    """The reported bug: V017 on one of the three files it reads together."""
    coverage = []
    found = RuleRegistry.check_file(str(path), None, path.read_text(encoding='utf-8'),
                                    select=['V017'], coverage=coverage)
    assert found == []
    assert [(c['rule'], c['status']) for c in coverage] == [('V017', 'skipped')], coverage


def test_reveal_own_tree_has_no_v_series_finding_file_by_file():
    """`reveal check reveal` as a dogfood: the V series answers on reveal:// alone."""
    offenders = []
    for path in sorted(_REVEAL_ROOT.rglob('*.py')):
        found = RuleRegistry.check_file(str(path), None, path.read_text(encoding='utf-8'), select=['V'])
        offenders.extend(f'{path.relative_to(_REVEAL_ROOT).as_posix()}: {d.rule_code} {d.message}'
                         for d in found)
    assert not offenders, offenders[:10]
