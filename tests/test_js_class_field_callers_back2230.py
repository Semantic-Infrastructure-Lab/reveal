"""A call in a class-field initializer has the field as its caller (BACK-2230).

`class K { handler = throttle(async () => helper(1)); plain = helper(2); }`: no listed function, method or
class owned either initializer, so `helper` showed "No callers found" (a function called only from a field read as
dead code, the failure BACK-334 fixed for test callbacks). The field is the caller, named like the oracle names it.
A field holding a function is already a listed method; a call inside a method stays that method's; BACK-1805 stays:
none of these is a `<module>` caller.
"""
import json
import os

import pytest

from conftest import _run_reveal_direct

DEFINITION = 'export function helper(x) { return x; }\n'
BODY = '''\
class K {
  handler = throttle(async () => helper(1));
  plain = helper(2);
  arrow = () => helper(3);
  static shared = debounce(() => { helper(4); });
  #secret = once(() => helper(5));
  run() { return [1].map((v) => helper(v)); }
}
'''
EXPECTED = {'handler', 'plain', 'arrow', 'shared', '#secret', 'run'}


def query(root, expression):
    out = _run_reveal_direct(f'calls://{root}?{expression}', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def callers_by_file(root, name='helper'):
    found = {}
    for level in query(root, f'callers={name}')['levels']:
        for c in level['callers']:
            found.setdefault(os.path.basename(c['file']), []).append(c['caller'])
    return found


@pytest.fixture(params=['js', 'ts'])
def project(tmp_path, request):
    (tmp_path / 'helper.js').write_text(DEFINITION, encoding='utf-8')
    (tmp_path / f'field.{request.param}').write_text(BODY, encoding='utf-8')
    return tmp_path


def test_every_field_initializer_call_has_the_field_as_caller_once(project):
    (name, got), = [(n, c) for n, c in callers_by_file(project).items() if n.startswith('field.')]
    assert sorted(got) == sorted(EXPECTED), name


def test_no_field_call_is_credited_to_the_module(project):
    assert '<module>' not in {c for cs in callers_by_file(project).values() for c in cs}


def test_a_field_is_a_caller_of_its_own_wrapper_too(project):
    got = callers_by_file(project, 'throttle')
    assert got and all(callers == ['handler'] for callers in got.values())


def test_callees_of_a_field_lists_what_its_initializer_calls(project):
    result = query(project, 'callees=handler')
    names = json.dumps(result)
    assert 'helper' in names and 'throttle' in names


def test_a_stale_cached_layer_without_the_field_key_is_rebuilt():
    from reveal.adapters.ast.analysis import _call_site_layer_complete
    old = {'module_call_sites': [], 'jsx_references': [], 'jsx_call_sites': []}
    assert not _call_site_layer_complete(old, 'js')
    assert _call_site_layer_complete({**old, 'class_field_call_sites': []}, 'js')
    assert _call_site_layer_complete({'module_call_sites': []}, 'python')
