"""BACK-1406 remainder: exits with no call node, and two effect false positives.

- PHP parses `exit;` / `exit(1)` as an exit_statement and a bare `die;` as a
  name statement; only `die("x")` (a call) was an exit, so --returns/--exits/
  --sideeffects missed 3 of the 4 forms.
- Ruby's bare `raise` / `exit` (no argument) is an identifier statement:
  --returns said "No return/exit paths" for a method with both.
- A receiver named `cursor` made any call db (`this.cursor.reset()`, a UI
  cursor); across the pinned corpora 457 of 467 `cursor.<verb>()` sites were
  not database calls.
- `process.env.hasOwnProperty(k)` was listed as an env var named
  `hasOwnProperty`.
"""

import textwrap

import pytest
import tree_sitter_language_pack as ts

from reveal.adapters.ast.nav_effects import classify_call, collect_effects, format_effect_target
from reveal.adapters.ast.nav_exits import collect_exits, collect_gate_chains
from reveal.core.treesitter_compat import tree_root, ts_parse

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


def _parse(language: str, code: str):
    source = textwrap.dedent(code).lstrip('\n')
    data = source.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser(language), source))

    def get_text(node):
        return data[node.start_byte:node.end_byte].decode('utf-8')

    return root, get_text


PHP = '''
<?php
function f($a) {
    if ($a == 1) { exit; }
    if ($a == 2) { exit(1); }
    if ($a == 3) { die("x"); }
    if ($a == 4) { die; }
    return 5;
}
'''

RUBY = '''
def f(a)
  begin
    x(a)
  rescue StandardError
    raise
  end
  exit if a == 2
  abort("no") if a == 3
  5
end
'''


def test_php_every_exit_form_is_an_exit_in_exits_and_returns():
    root, get_text = _parse('php', PHP)
    expected = [('EXIT', 3), ('EXIT', 4), ('EXIT', 5), ('EXIT', 6), ('RETURN', 7)]
    assert [(e['kind'], e['line']) for e in collect_exits(root, 1, 99, get_text)] == expected
    chains = collect_gate_chains(root, 1, 99, get_text)
    assert [(e['kind'], e['line']) for e in chains] == expected
    assert chains[0]['text'] == 'exit;' and chains[3]['text'] == 'die'


def test_ruby_bare_raise_exit_and_abort_are_exits():
    root, get_text = _parse('ruby', RUBY)
    assert [(e['kind'], e['line'], e['text']) for e in collect_gate_chains(root, 1, 99, get_text)] == [
        ('EXIT', 5, 'raise'), ('EXIT', 7, 'exit'), ('EXIT', 8, 'abort("no")'),
    ]


@pytest.mark.parametrize('language, code', [
    ('python', 'def f():\n    exit\n    die\n'),           # a bare name is a no-op expression
    ('javascript', 'function f() { exit; die; }\n'),
    ('ruby', 'def f\n  foo(exit)\nend\n'),                   # an argument, not a statement
])
def test_bare_exit_name_needs_statement_position_in_its_own_language(language, code):
    root, get_text = _parse(language, code)
    assert collect_exits(root, 1, 99, get_text) == []


def test_php_exit_statements_are_hard_stop_effects_rendered_as_written():
    root, get_text = _parse('php', PHP)
    effects = [e for e in collect_effects(root, 1, 99, get_text, language='php')
               if e['kind'] == 'hard_stop']
    assert [(e['line'], format_effect_target(e)) for e in effects] == [
        (3, 'exit'), (4, 'exit(1)'), (5, 'die("x")'), (6, 'die'),
    ]


def test_statement_channel_is_php_only():
    """Ruby's bare `exit` is already a call site (the analyzer's implicit
    calls); the statement channel must not report it a second time."""
    from reveal.adapters.ast.nav_effects import _collect_statement_exits
    root, get_text = _parse('ruby', RUBY)
    assert _collect_statement_exits(root, 1, 99, get_text) == []


@pytest.mark.parametrize('callee, expected', [
    ('cursor.execute', 'db'), ('self.cursor.fetchall', 'db'), ('db.cursor.executemany', 'db'),
    ('this.cursor.reset', None), ('cursor.gotoFirstChild', None), ('cursor.remaining', None),
    ('cursor.move_on_next', None), ('db.users.find', 'db'),
])
def test_cursor_receiver_counts_only_db_api_verbs(callee, expected):
    assert classify_call(callee, 'javascript') == expected
    assert classify_call(callee, 'python') == expected


def test_process_env_method_call_is_not_an_env_var(tmp_path):
    from reveal.adapters.ast.nav_surface_ts import scan_file_surface_ts
    path = tmp_path / 'c.js'
    path.write_text('if (process.env.hasOwnProperty(k)) { use(process.env.NODE_ENV); }\n'
                    'const s = process.env.toString();\n', encoding='utf-8')
    assert [e['name'] for e in scan_file_surface_ts(str(path))['env']] == ['NODE_ENV']
