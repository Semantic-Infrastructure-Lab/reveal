"""BACK-1331: surface:// rule engine, and conformance generated from the rule tables.

Replaces the hand-written cross-language table from BACK-1319. Every `Rule` carries an
`example` that must match it and `counter_examples` that must match nothing, so adding a
row adds its test and coverage cannot rot. The generated tests run through the real
`surface://` scan of a file, not just the engine, so the scanner wiring is covered too.
"""

import pytest

from reveal.adapters.ast import surface_rules as sr
from reveal.adapters.ast.surface_facts import Call as CallFact
from reveal.adapters.ast.surface_facts import extract_facts
from reveal.adapters.surface import _scan_surface

EXT = {'python': 'py', 'go': 'go', 'java': 'java', 'kotlin': 'kt', 'ruby': 'rb',
       'rust': 'rs', 'csharp': 'cs', 'swift': 'swift'}
RULES = sr.all_rules()
RULE_IDS = [f'{r.category}-{r.lang}-{i}' for i, r in enumerate(RULES)]


def _scan(lang, code, tmp_path, category):
    path = tmp_path / f'sample.{EXT[lang]}'
    path.write_text(code, encoding='utf-8')
    return _scan_surface(path)['surfaces'][category]


def _rules_of(lang, code, category='subprocess'):
    return sr.rule_matches(sr.rules_for(category, lang), extract_facts(code, lang))


# ── generated from the tables ───────────────────────────────────────────────

@pytest.mark.parametrize('rule', RULES, ids=RULE_IDS)
def test_example_matches_its_own_rule(rule):
    matched = [r for r, _f, _n in _rules_of(rule.lang, rule.example, rule.category)]
    assert rule in matched, f'{rule.lang}: example did not match {rule.match}; matched {matched}'


@pytest.mark.parametrize('rule', RULES, ids=RULE_IDS)
def test_example_is_reported_by_the_scanner(rule, tmp_path):
    assert _scan(rule.lang, rule.example, tmp_path, rule.category), \
        f'{rule.lang}: surface:// reports no {rule.category} entry for the rule example'


COUNTER_CASES = [(r, i, c) for r in RULES for i, c in enumerate(r.counter_examples)]


@pytest.mark.parametrize('rule,i,code', COUNTER_CASES,
                         ids=[f'{r.category}-{r.lang}-cx{i}' for r, i, _c in COUNTER_CASES])
def test_counter_example_reports_nothing(rule, i, code, tmp_path):
    assert _scan(rule.lang, code, tmp_path, rule.category) == []


@pytest.mark.parametrize('rule', RULES, ids=RULE_IDS)
def test_every_site_the_scanner_reports_has_a_fact_on_its_line(rule, tmp_path):
    entries = _scan(rule.lang, rule.example, tmp_path, rule.category)
    fact_lines = {f.line for f in extract_facts(rule.example, rule.lang) if hasattr(f, 'line')}
    assert {e['line'] for e in entries} <= fact_lines


def test_subprocess_is_rule_driven_for_the_eight_pilot_languages():
    """A language silently dropping out of the table would read as `subprocess: 0`."""
    assert {r.lang for r in RULES if r.category == 'subprocess'} == set(EXT)
    for lang in EXT:
        assert 'subprocess' in sr.rule_categories(lang)


@pytest.mark.parametrize('rule', [r for r in RULES if r.lang != 'python'],
                         ids=[i for r, i in zip(RULES, RULE_IDS) if r.lang != 'python'])
def test_prefilter_never_drops_a_site_a_rule_matches(rule):
    """The scanners feed facts through a filter built from the tables; it must be a superset."""
    want_call, want_new = sr._call_filter(rule.lang), sr._new_filter(rule.lang)
    for r, fact, _name in _rules_of(rule.lang, rule.example, rule.category):
        if isinstance(fact, CallFact) and want_call is not None:
            assert want_call(fact.receiver, fact.name), f'{r.match} dropped {fact}'
        if hasattr(fact, 'type_name') and want_new is not None:
            assert want_new(fact.type_name), f'{r.match} dropped {fact}'


def test_prefilter_is_disabled_by_a_rule_that_could_match_any_call():
    rules = (_rule(sr.Call(receiver='exec')),)     # nameless and not pinned to a receiver
    saved = sr._TABLES.copy()
    try:
        sr._TABLES['subprocess'] = rules
        sr._reset_caches()
        assert sr._call_filter('go') is not None    # pinned to a receiver: still filterable
        sr._TABLES['subprocess'] = (_rule(sr.Call()),)
        sr._reset_caches()
        assert sr._call_filter('go') is None
    finally:
        sr._TABLES.clear()
        sr._TABLES.update(saved)
        sr._reset_caches()


def test_python_scan_without_source_does_not_gate(tmp_path):
    """`source` is an optimisation hint; leaving it out must not lose sites."""
    import ast
    surfaces = {'subprocess': []}
    sr.apply_ast_rules(surfaces, ast.parse('import os\nos.system("x")\n'), 'x.py')
    assert [e['name'] for e in surfaces['subprocess']] == ['os.system']
    gated = {'subprocess': []}
    sr.apply_ast_rules(gated, ast.parse('x = 1\n'), 'x.py', 'x = 1\n')
    assert gated['subprocess'] == []


@pytest.mark.parametrize('lang,code', [
    # one of the gate's literals only appears in an identifier the rule cares about
    ('java', 'class A { void f() throws Exception { Runtime.getRuntime().exec("a"); } }\n'),
    ('ruby', 'def f\n  Open3.capture2("a")\nend\n'),
    ('kotlin', 'fun f() { Runtime.getRuntime().exec("a") }\n'),
    ('swift', 'import Foundation\nfunc f() { let p = NSTask() }\n'),
], ids=['java', 'ruby-receiver-only', 'kotlin', 'swift'])
def test_needle_gate_never_hides_a_match(lang, code, tmp_path):
    assert _scan(lang, code, tmp_path, 'subprocess')
    assert any(n in code.encode() for n in sr._needles(lang))


# ── engine semantics ────────────────────────────────────────────────────────

def _rule(match, name='{path}', lang='go', requires=None, example='package main\nfunc f(){ a.b() }\n'):
    return sr.Rule('subprocess', lang, match, name, example, requires=requires)


def _entries(rules, code, lang='go'):
    return [n for _r, _f, n in sr.rule_matches(rules, extract_facts(code, lang))]


def test_first_matching_rule_wins_per_site():
    code = 'package main\nfunc f(){ exec.Command("a") }\n'
    rules = (_rule(sr.Call(receiver='exec'), name='first'), _rule(sr.Call(name='Command'), name='second'))
    assert _entries(rules, code) == ['first']


def test_scan_category_dedupes_on_name_and_line():
    code = 'package main\nfunc f(){ exec.Command("a"); exec.Command("b") }\n'
    facts = extract_facts(code, 'go')
    assert len(sr.scan_category('subprocess', 'go', facts, 'x.go')) == 1


def test_name_globs():
    code = 'import os\nos.execvp("a")\nos.executable\nos.getcwd()\n'
    rules = (_rule(sr.Call(resolved=True, receiver='os', name='exec*'), lang='python'),)
    assert _entries(rules, code, 'python') == ['os.execvp']


def test_bare_receiver_does_not_match_a_call_on_a_call_result():
    """`a.b().exec()` has receiver '' after chain collapse, but it is not a bare `exec()`."""
    bare = (_rule(sr.Call(receiver='', name='exec'), lang='ruby'),)
    assert _entries(bare, 'def f\n  exec("x")\nend\n', 'ruby') == ['exec']
    assert _entries(bare, 'def f\n  a.b.exec("x")\nend\n', 'ruby') == []
    assert _entries(bare, 'def f\n  Conn.connection.raw.exec("x")\nend\n', 'ruby') == []


def test_qualified_match_keeps_the_receiver_chain():
    rules = (_rule(sr.Call(qualified='Runtime.getRuntime().exec'), lang='java'),)
    hit = 'class A { void f() throws Exception {\n Runtime.getRuntime()\n   .exec("x"); } }\n'
    miss = 'class A { void f(Runtime r) throws Exception { r.exec("x"); other().exec("y"); } }\n'
    assert _entries(rules, hit, 'java') == ['exec']
    assert _entries(rules, miss, 'java') == []


def test_imported_from_is_segment_aligned():
    rules = (_rule(sr.Call(receiver='Command', name='new'), lang='rust',
                   requires=sr.ImportedFrom('process::Command')),)
    call = 'fn f(){ Command::new("a"); }\n'
    assert _entries(rules, 'use std::process::Command;\n' + call, 'rust') == ['Command::new']
    assert _entries(rules, 'use std::process::{self, Command};\n' + call, 'rust') == ['Command::new']
    assert _entries(rules, 'use clap::Command;\n' + call, 'rust') == []
    assert _entries(rules, 'use myprocess::Command;\n' + call, 'rust') == []


def test_resolved_call_follows_import_aliases_and_needs_an_import():
    rules = (_rule(sr.Call(resolved=True, receiver='subprocess', name='run'), lang='python'),
             _rule(sr.Call(resolved=True, receiver='os', name='system'), lang='python'))
    aliased = 'import subprocess as sp\nfrom os import system as sh\nsp.run(["a"])\nsh("b")\n'
    assert _entries(rules, aliased, 'python') == ['subprocess.run', 'os.system']
    assert _entries(rules, 'def run(x): ...\nrun(1)\nc.system()\n', 'python') == []


def test_new_subshell_and_import_match_kinds():
    assert _entries((_rule(sr.New(type='ProcessBuilder'), name='new {type}()', lang='java'),),
                    'class A { void f(){ new ProcessBuilder("a"); new Other(); } }\n', 'java') \
        == ['new ProcessBuilder()']
    assert _entries((_rule(sr.Subshell(), name='`...`', lang='ruby'),),
                    'def f\n  `ls`\n  %x(pwd)\nend\n', 'ruby') == ['`...`', '`...`']
    imp = (_rule(sr.Import(module='child_process'), name='{module}', lang='typescript'),)
    assert _entries(imp, 'import { spawn } from "child_process";\nimport x from "child_processes";\n',
                    'typescript') == ['child_process']


# ── rule validation ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('kwargs,message', [
    (dict(category='nope'), 'unknown category'),
    (dict(lang='cobol'), 'unknown language'),
    (dict(example='   '), 'needs an example'),
    (dict(entry_name='{receiver}'), 'not offered by'),
], ids=['category', 'lang', 'example', 'placeholder'])
def test_rule_rejects_malformed_rows(kwargs, message):
    base = dict(category='subprocess', lang='go', match=sr.Subshell(), entry_name='x', example='x')
    with pytest.raises(ValueError, match=message):
        sr.Rule(**{**base, **kwargs})


def test_register_table_rejects_a_foreign_category():
    with pytest.raises(ValueError, match='table holds rules'):
        sr.register_table('fs', (_rule(sr.Subshell(), name='x', lang='ruby'),))


# ── deliberate differences from the scanners this replaced (BACK-1331 parity notes) ──

@pytest.mark.parametrize('lang,code,expected', [
    # Rust: the old check was a regex over the whole file, so a commented-out import counted.
    ('rust', 'fn f(){ Command::new("a"); }\n// use std::process::Command;\n', []),
    # Ruby: `Open3::popen3` (scope form) is a call too; the old scanner only saw the `.` form.
    ('ruby', 'def f\n  Open3::capture3("k")\nend\n', ['Open3.capture3']),
    # Ruby: `Kernel::system` is named like `Kernel.system`; it used to surface as bare `system`.
    ('ruby', 'def f\n  Kernel::system("a")\nend\n', ['Kernel.system']),
    # Python: `import os.path` still binds `os` to the os module (old map bound it to os.path).
    ('python', 'import os.path\nos.system("x")\n', ['os.system']),
    # Python: a relative `from . import os` is a local module, not the stdlib one.
    ('python', 'from . import os\nos.system("x")\n', []),
], ids=['rust-comment', 'ruby-scope-call', 'ruby-kernel-scope', 'python-os-path', 'python-relative'])
def test_documented_parity_deltas(lang, code, expected, tmp_path):
    assert sorted(e['name'] for e in _scan(lang, code, tmp_path, 'subprocess')) == expected
