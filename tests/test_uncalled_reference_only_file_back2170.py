"""?uncalled sees references in files that define no function or class (BACK-2170).

A file of top-level statements (WordPress `default-filters.php`: a list of `add_action('x', 'fn')`)
has an empty structure, so collect_structures omits it, and the referenced-names pass that reads
`structures` never opened it: every function it names read as dead.
"""
import json

from conftest import _run_reveal_direct

DEFS = '<?php\nfunction on_delete($id) {}\nfunction on_other($id) {}\nfunction unused_one() {}\n'
HOOKS = "<?php\nadd_action('delete_attachment', 'on_delete');\nadd_filter('x', 'on_other', 10, 2);\n"
JS_DEFS = 'function onTick() { return 1; }\nfunction orphan() { return 2; }\n'
JS_USE = 'setInterval(onTick, 10);\n'


def uncalled(tmp_path, files):
    root = tmp_path / 'proj'
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding='utf-8')
    out = _run_reveal_direct(f'calls://{root}?uncalled=true', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return sorted(e['name'] for e in json.loads(out.stdout)['entries'])


def test_php_hook_strings_in_a_function_less_file_reference_the_functions(tmp_path):
    assert uncalled(tmp_path, {'a.php': DEFS, 'b.php': HOOKS}) == ['unused_one']


def test_js_callback_in_a_function_less_file_references_the_function(tmp_path):
    assert 'onTick' not in uncalled(tmp_path, {'a.js': JS_DEFS, 'main.js': JS_USE})


def test_control_unreferenced_php_functions_stay_reported(tmp_path):
    assert uncalled(tmp_path, {'a.php': DEFS, 'b.php': "<?php\nadd_action('x', 'someone_else');\n"}) \
        == ['on_delete', 'on_other', 'unused_one']


def test_control_unreferenced_js_function_stays_reported(tmp_path):
    assert 'orphan' in uncalled(tmp_path, {'a.js': JS_DEFS, 'main.js': JS_USE})
