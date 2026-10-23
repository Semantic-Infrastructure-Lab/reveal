"""A class-field arrow method that another file calls is not uncalled, even when the call has no named caller (BACK-2180).

`?uncalled` first asks the caller index; a function nobody is recorded as calling then goes through the
reference pass, which counts the name's occurrences and subtracts the definitions the scan found. A class
field (`public dismiss = () => {}`) is a definition, but the pass skipped its own name as a "member
binding", so one real use (`app.dismiss()` inside a module-level `setTimeout` callback, which has no named
caller) balanced one definition and the method was reported uncalled. Found when BACK-2174 stopped
attributing the calls inside a plain-call value's callback to that value.
"""
import json

import pytest

from conftest import _run_reveal_direct

FIELD = '''\
export class App {
  public dismiss = () => { return 1; };
  public neverUsed = () => { return 2; };
  public viaMethod() { return 3; }
}
'''
USER = '''\
declare const app: any;
setTimeout(() => { app.dismiss(); }, 10);
export const act = register({
  perform: () => {
    const found = findThing(app, () => { app.viaMethod(); return 1; });
    return found;
  },
});
'''


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'app.ts').write_text(FIELD, encoding='utf-8')
    (root / 'use.ts').write_text(USER, encoding='utf-8')
    return root


def uncalled(project):
    out = _run_reveal_direct(f'calls://{project}?uncalled=true', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return {e['name'] for e in json.loads(out.stdout)['entries']}


def test_a_class_field_method_called_from_an_unattributed_scope_is_not_uncalled(project):
    assert 'dismiss' not in uncalled(project)


def test_a_method_called_inside_the_callback_of_a_plain_call_value_is_not_uncalled(project):
    assert 'viaMethod' not in uncalled(project)


def test_a_class_field_method_nobody_calls_is_still_reported(project):
    assert 'neverUsed' in uncalled(project)
