"""Scoped var-flow WRITE facts remain local for shared-storage resolution."""
import pytest

from reveal.adapters.ast.nav_bindings import BindingScope
from reveal.adapters.ast.nav_statewrites import collect_statewrites
from reveal.core.treesitter_compat import iter_tree, _zero_arg
from test_binders_back1897 import parsed


@pytest.mark.parametrize('header', [
    'for (let state = {}; ready; tick())',
    'for (const state of items)',
    'for (let state in items)',
])
def test_loop_container_shadows_module_only_inside_scope(header):
    scope, text, end = parsed('javascript', f'''\
let state = {{}};
function target(key) {{
 {header} {{
   state[key] = 1;
   const write = () => {{ state[key] = 2; }};
   write();
 }}
 state[key] = 3;
}}
''')
    assert collect_statewrites(scope, 1, end, text, 'javascript') == [
        {'kind': 'global', 'line': 8, 'target': 'state[key]', 'via': 'assignment'}]
    assert collect_statewrites(scope, 1, end, text, 'javascript') == [
        {'kind': 'global', 'line': 8, 'target': 'state[key]', 'via': 'assignment'}]
    facts = BindingScope(scope, text, 'javascript')
    targets = [n for n in iter_tree(scope) if _zero_arg(n, 'kind') == 'subscript_expression'
               and text(n) == 'state[key]']
    assert [facts.shared_write_kind(target) for target in targets] == [None, None, 'global']
