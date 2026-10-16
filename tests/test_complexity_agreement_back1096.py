"""One function, one complexity number (BACK-1096, audit section 3 / item 5).

The 2026-08-10 consistency audit found C901 and ast://stats:// reporting 30 vs 24
for the same function.  They now read one score from the analyzer's structure;
this pins that no consumer recomputes it.  Four readers must agree per function:
the analyzer structure, ast://?complexity>0, stats:// and C901 (threshold 0).
A disagreement proves one is wrong without saying which.
"""
import re

import pytest

import reveal.analyzers  # noqa: F401  (registers every analyzer)
from reveal.adapters.ast import AstAdapter
from reveal.adapters.stats import StatsAdapter
from reveal.cli.file_checker import check_and_collect_file
from reveal.config import RevealConfig
from reveal.registry import get_analyzer
from reveal.rules import RuleRegistry

pytestmark = [pytest.mark.component]

# One branchy function `f` per language: if, &&/||, a loop, an exception or
# switch arm and a ternary, so a consumer that drops any decision point shows.
SOURCES = {
    'a.py': 'def f(x, y):\n    if x and y or x:\n        for i in x:\n            try:\n                pass\n'
            '            except ValueError:\n                pass\n    return [i for i in y if i]\n',
    'a.js': 'function f(x, y) {\n  if (x && y || x) {\n    for (const i of x) { try { g(); } catch (e) { h(); } }\n'
            '  }\n  return y ? 1 : 2;\n}\n',
    'a.go': 'package d\nfunc f(x, y int) int {\n\tif x > 0 && y > 0 || x < 0 {\n\t\tfor i := 0; i < x; i++ {\n'
            '\t\t\tswitch y {\n\t\t\tcase 1:\n\t\t\t\treturn 1\n\t\t\tcase 2:\n\t\t\t\treturn 2\n\t\t\t}\n\t\t}\n\t}\n\treturn 0\n}\n',
    'a.java': 'class W {\n int f(int x, int y) {\n  if (x > 0 && y > 0 || x < 0) {\n   for (int i = 0; i < x; i++) {\n'
              '    try { g(); } catch (Exception e) { h(); }\n   }\n  }\n  return y > 0 ? 1 : 2;\n }\n}\n',
    'a.rs': 'fn f(x: i32, y: i32) -> i32 {\n    if x > 0 && y > 0 || x < 0 {\n        for i in 0..x {\n'
            '            match y { 1 => return 1, 2 => return 2, _ => {} }\n        }\n    }\n    0\n}\n',
    'a.rb': 'def f(x, y)\n  if x && y || x\n    x.each do |i|\n      begin\n        g\n      rescue StandardError\n'
            '        h\n      end\n    end\n  end\n  y ? 1 : 2\nend\n',
    'a.c': 'int f(int x, int y) {\n  if (x > 0 && y > 0 || x < 0) {\n    for (int i = 0; i < x; i++) {\n'
           '      switch (y) { case 1: return 1; case 2: return 2; }\n    }\n  }\n  return y ? 1 : 2;\n}\n',
}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    # RevealConfig caches the merged config per project root, env overrides included:
    # without the clear, threshold 0 outlives the monkeypatch and every later C901 test
    # in this xdist worker sees "max: 0".
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    monkeypatch.setenv('REVEAL_C901_THRESHOLD', '0')
    RevealConfig._cache.clear()
    yield
    RevealConfig._cache.clear()


def _structure_complexity(path):
    analyzer = get_analyzer(str(path))(str(path))
    return {f['name']: f.get('complexity') for f in analyzer.get_structure().get('functions', [])}


def _ast_complexity(path):
    results = AstAdapter(str(path.parent), 'complexity>0').get_structure()['results']
    return {r['name']: r['complexity'] for r in results if r['file'].endswith(path.name)}


def _stats_complexity(path):
    (entry,) = StatsAdapter(str(path)).get_structure()['files']
    return {'max': entry['complexity']['max'], 'min': entry['complexity']['min']}


def _c901_complexity(path):
    RuleRegistry.discover()
    _, detections, status = check_and_collect_file(path, path.parent, ['C901'], None)
    assert status['status'] in ('ok', 'warning'), status
    found = {}
    for d in detections:
        m = re.search(r'too complex: (\S+) \(complexity: (\d+)', d.message)
        found[m.group(1)] = int(m.group(2))
    return found


@pytest.mark.parametrize('name', sorted(SOURCES))
def test_every_reader_reports_the_same_complexity(tmp_path, name):
    path = tmp_path / name
    path.write_text(SOURCES[name], encoding='utf-8')
    expected = _structure_complexity(path)
    assert expected.get('f', 0) >= 5, ('positive control: f must be branchy', expected)
    assert _ast_complexity(path) == expected
    assert _c901_complexity(path) == expected
    stats = _stats_complexity(path)
    assert stats['max'] == stats['min'] == expected['f']


def test_the_guard_notices_a_reader_that_falls_back_to_the_heuristic(tmp_path):
    """Negative control: C901 on a structure without a score uses the fallback
    heuristic, which gives Go 3 where the analyzer says 7, so the equality above
    would fail if any reader took that path for a function the analyzer scored."""
    path = tmp_path / 'a.go'
    path.write_text(SOURCES['a.go'], encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    structure = analyzer.get_structure()
    scored = {f['name']: f['complexity'] for f in structure['functions']}
    for func in structure['functions']:
        func['complexity'] = None
    RuleRegistry.discover()
    rule = RuleRegistry.get_configured_rule('C901', str(path))
    stripped = {}
    for d in rule.check(str(path), structure, analyzer.content):
        name, value = d.message.split('too complex: ')[1].split(' (complexity: ')
        stripped[name] = int(value.split(',')[0])
    assert stripped != scored
