"""A method's own name binds nothing in its body (BACK-2198).

`const normal = Fn(...)` is a function when this file calls `normal`. `_node_rebinds` read a
`method_definition`'s name as a binding inside its body, so a method called `normal` made the call
`normal(...)` in that body look like a call of the method's own name and the module-level `normal`
was dropped (three.js `Texture3DNode`). In JS a method name is a property key; only function
declarations and expressions bind their own name inside. A method's parameters still shadow.
"""
import json

import pytest

from conftest import _run_reveal_direct

FN = '''\
const normal = Fn( ( { texture, uv } ) => {
	return texture.sample( uv ).mul( 2 );
} );
'''
SAME_NAME = FN + '''\
class Texture3DNode {
	normal( uvNode ) {
		return normal( { texture: this, uv: uvNode } );
	}
}
'''
OTHER_NAME = FN + '''\
class Texture3DNode {
	normalAt( uvNode ) {
		return normal( { texture: this, uv: uvNode } );
	}
}
'''
PARAM_SHADOWS = FN + '''\
class Texture3DNode {
	normalAt( normal ) {
		return normal( 1 );
	}
}
'''


def module_level_names(tmp_path, source):
    """Names of the functions that belong to no class: the `const normal = Fn(...)` value is one,
    a method called `normal` is not (it has an owner), so a same-named method cannot stand in for it."""
    path = tmp_path / 'a.js'
    path.write_text(source, encoding='utf-8')
    out = _run_reveal_direct(str(path), '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return {f['name'] for f in json.loads(out.stdout)['structure']['functions'] if not f.get('owner')}


def test_a_method_named_like_the_called_value_does_not_hide_it(tmp_path):
    assert 'normal' in module_level_names(tmp_path, SAME_NAME)


def test_the_control_with_a_differently_named_method_keeps_it(tmp_path):
    assert 'normal' in module_level_names(tmp_path, OTHER_NAME)


@pytest.mark.parametrize('source', [PARAM_SHADOWS])
def test_a_method_parameter_of_that_name_still_shadows(tmp_path, source):
    assert 'normal' not in module_level_names(tmp_path, source)
