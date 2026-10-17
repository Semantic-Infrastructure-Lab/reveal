"""GDScript constructors use the indexed named/line/ordinal extraction span."""

import pytest

from reveal.display.element import (
    _extract_by_name, _extract_element_at_line, _extract_ordinal_element,
)
from reveal.registry import get_analyzer

pytestmark = pytest.mark.component


@pytest.fixture(params=['script', 'nested', 'single_line'])
def constructor(request, tmp_path):
    cases = {
        'script': (
            'extends Node\nvar value = 0\n\n'
            'func _init(seed = 1):\n    value = seed\n'
            '    if seed:\n        value += 1\n\n'
            'func ordinary():\n    return value\n',
            {'name': '_init', 'line_start': 4, 'line_end': 7,
             'source': 'func _init(seed = 1):\n    value = seed\n'
                       '    if seed:\n        value += 1'},
            {'name': 'ordinary', 'line_start': 9, 'line_end': 10,
             'source': 'func ordinary():\n    return value'},
        ),
        'nested': (
            'extends Node\nclass Inner:\n    var marker = 0\n'
            '    func _init(seed = 2):\n        marker = seed\n\n'
            '    func ordinary():\n        return marker\n',
            {'name': '_init', 'line_start': 4, 'line_end': 5,
             'source': '    func _init(seed = 2):\n        marker = seed'},
            {'name': 'ordinary', 'line_start': 7, 'line_end': 8,
             'source': '    func ordinary():\n        return marker'},
        ),
        'single_line': (
            'extends Node\nvar value = 0\n'
            'func _init(): value = 1; value += 2\n'
            'func ordinary(): return value\n',
            {'name': '_init', 'line_start': 3, 'line_end': 3,
             'source': 'func _init(): value = 1; value += 2'},
            {'name': 'ordinary', 'line_start': 4, 'line_end': 4,
             'source': 'func ordinary(): return value'},
        ),
    }
    source, expected, ordinary = cases[request.param]
    path = tmp_path / 'constructor.gd'
    path.write_text(source, encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    assert not analyzer._has_recovery_artifacts()
    return analyzer, expected, ordinary


def test_named_constructor_matches_manual_span(constructor):
    analyzer, expected, _ = constructor
    assert _extract_by_name(analyzer, '_init') == expected


def test_constructor_declaration_body_and_last_line_match_named(constructor):
    analyzer, expected, _ = constructor
    for _ in range(2):
        for line in range(expected['line_start'], expected['line_end'] + 1):
            assert _extract_element_at_line(analyzer, line) == expected


def test_constructor_ordinal_keeps_exact_source(constructor):
    analyzer, expected, _ = constructor
    assert _extract_ordinal_element(analyzer, 1, 'function') == expected


def test_ordinary_function_sibling_keeps_its_span(constructor):
    analyzer, _, ordinary = constructor
    assert _extract_by_name(analyzer, 'ordinary') == ordinary
    assert _extract_ordinal_element(analyzer, 2, 'function') == ordinary
    for line in range(ordinary['line_start'], ordinary['line_end'] + 1):
        assert _extract_element_at_line(analyzer, line) == ordinary


@pytest.mark.parametrize('line', [1, 2, 3, 4, 5, 6, 9])
def test_nondefinition_and_anonymous_siblings_do_not_become_constructors(tmp_path, line):
    path = tmp_path / 'siblings.gd'
    path.write_text(
        'extends Node\n# Header comment.\nvar value = 0\n'
        'var label = "_init"\nvar callback = func(): return 1\n\n'
        'func _init():\n    value = 1\n\n'
        'func ordinary():\n    return value\n', encoding='utf-8',
    )
    analyzer = get_analyzer(str(path))(str(path))
    assert not analyzer._has_recovery_artifacts()
    assert _extract_element_at_line(analyzer, line) is None
