"""?uncalled sees a PHP handler reached through a computed callback name (BACK-2175).

WordPress `admin-ajax.php` lists its actions as strings and dispatches
`do_action('wp_ajax_' . str_replace('-', '_', $action))`: no `wp_ajax_*` name ever appears
as one literal, so every handler read as dead. A literal prefix concatenated to a computed
value, in a file that also lists a string naming the rest, references `prefix + rest`.
"""
import json

from conftest import _run_reveal_direct

DEFS = ('<?php\nfunction wp_ajax_fetch_list() {}\nfunction wp_ajax_other_thing() {}\n'
        'function wp_ajax_never_listed() {}\nfunction unused_one() {}\n')
DISPATCH = ("<?php\n$core_actions_get = array('fetch-list', 'other_thing');\n"
            "do_action('wp_ajax_' . str_replace('-', '_', $action));\n")
INTERPOLATED = ("<?php\n$actions = array('fetch-list', 'other-thing');\n"
                'do_action("wp_ajax_{$action}");\n')


def uncalled(tmp_path, files):
    root = tmp_path / 'proj'
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding='utf-8')
    out = _run_reveal_direct(f'calls://{root}?uncalled=true', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return sorted(e['name'] for e in json.loads(out.stdout)['entries'])


def test_prefix_plus_computed_value_references_the_listed_handlers(tmp_path):
    assert uncalled(tmp_path, {'a.php': DEFS, 'ajax.php': DISPATCH}) == ['unused_one', 'wp_ajax_never_listed']


def test_control_interpolated_hook_name_references_nothing(tmp_path):
    files = {'a.php': DEFS, 'ajax.php': INTERPOLATED}
    assert uncalled(tmp_path, files) == ['unused_one', 'wp_ajax_fetch_list', 'wp_ajax_never_listed', 'wp_ajax_other_thing']


def test_control_listed_strings_without_a_prefix_use_reference_nothing(tmp_path):
    files = {'a.php': DEFS, 'ajax.php': "<?php\n$actions = array('fetch-list', 'other_thing');\n"}
    assert uncalled(tmp_path, files) == ['unused_one', 'wp_ajax_fetch_list', 'wp_ajax_never_listed', 'wp_ajax_other_thing']


def test_control_prefix_without_a_listed_string_references_nothing(tmp_path):
    files = {'a.php': DEFS, 'ajax.php': "<?php\ndo_action('wp_ajax_' . $action);\n"}
    assert uncalled(tmp_path, files) == ['unused_one', 'wp_ajax_fetch_list', 'wp_ajax_never_listed', 'wp_ajax_other_thing']
