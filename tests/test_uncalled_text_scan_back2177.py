"""The computed-callback and reflected-annotation checks read the parse tree, not raw text (BACK-2177).

A PHP `'prefix_' . $x` or an action string inside a comment, and a Java `@interface X` or
`isAnnotationPresent(X.class)` inside a comment or string literal, are not code: they must not
reference a handler or mark a method as an entry point.
"""
import json

from conftest import _run_reveal_direct

PHP_DEFS = '<?php\nfunction wp_ajax_fetch_list() {}\n'
PHP_COMMENT_ONLY = "<?php\n// do_action('wp_ajax_' . $action);  $x = array('fetch-list');\n/* do_action('wp_ajax_' . $a); */\n"
PHP_PREFIX_CODE_LIST_COMMENT = "<?php\ndo_action('wp_ajax_' . $action);\n// array('fetch-list')\n"
PHP_PREFIX_COMMENT_LIST_CODE = "<?php\n// do_action('wp_ajax_' . $action);\n$a = array('fetch-list');\n"
PHP_REAL = "<?php\n$a = array('fetch-list');\ndo_action('wp_ajax_' . $action);\n"

JAVA_USER = 'package p;\nclass Gen { @Generates int makeInt() { return 1; } }\n'
JAVA_DECL = 'package p;\n@interface Generates {}\n'
JAVA_DECL_COMMENT = 'package p;\n// @interface Generates {}\n/* @interface Generates {} */\n'
JAVA_READ = 'package p;\nclass R { boolean w(java.lang.reflect.Method m) { return m.isAnnotationPresent(Generates.class); } }\n'
JAVA_READ_TEXT = ('package p;\nclass R { String doc = "m.isAnnotationPresent(Generates.class)";\n'
                  '  // m.getAnnotation(Generates.class)\n}\n')


def uncalled(tmp_path, files):
    root = tmp_path / 'proj'
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding='utf-8')
    out = _run_reveal_direct(f'calls://{root}?uncalled=true', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return sorted(e['name'] for e in json.loads(out.stdout)['entries'])


def test_php_prefix_and_action_in_comments_reference_nothing(tmp_path):
    assert uncalled(tmp_path, {'a.php': PHP_DEFS, 'b.php': PHP_COMMENT_ONLY}) == ['wp_ajax_fetch_list']


def test_php_prefix_in_code_with_the_list_in_a_comment_references_nothing(tmp_path):
    assert uncalled(tmp_path, {'a.php': PHP_DEFS, 'b.php': PHP_PREFIX_CODE_LIST_COMMENT}) == ['wp_ajax_fetch_list']


def test_php_prefix_in_a_comment_with_the_list_in_code_references_nothing(tmp_path):
    assert uncalled(tmp_path, {'a.php': PHP_DEFS, 'b.php': PHP_PREFIX_COMMENT_LIST_CODE}) == ['wp_ajax_fetch_list']


def test_control_php_prefix_and_list_in_code_still_reference_the_handler(tmp_path):
    assert uncalled(tmp_path, {'a.php': PHP_DEFS, 'b.php': PHP_REAL}) == []


def test_java_annotation_declared_only_in_a_comment_marks_nothing(tmp_path):
    files = {'Gen.java': JAVA_USER, 'D.java': JAVA_DECL_COMMENT, 'R.java': JAVA_READ}
    assert 'makeInt' in uncalled(tmp_path, files)


def test_java_reflection_read_only_in_a_string_or_comment_marks_nothing(tmp_path):
    files = {'Gen.java': JAVA_USER, 'D.java': JAVA_DECL, 'R.java': JAVA_READ_TEXT}
    assert 'makeInt' in uncalled(tmp_path, files)


def test_control_java_declared_and_read_in_code_still_marks_the_method(tmp_path):
    files = {'Gen.java': JAVA_USER, 'D.java': JAVA_DECL, 'R.java': JAVA_READ}
    assert 'makeInt' not in uncalled(tmp_path, files)
