"""BACK-1283: Python-only features are declared, and warn when run over other languages."""

import pytest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.capabilities import (
    PYTHON_ONLY_FEATURES,
    W_CAP_PYTHON_ONLY,
    get_capability_for_extension,
    python_only_warning,
)
from reveal.rendering.adapters.ast import _render_dict_heatmap

pytestmark = pytest.mark.component

PY = 'def f(cfg):\n    return cfg["a"] + cfg["b"]\n\ndef g(cfg):\n    return cfg["a"]\n'


@pytest.fixture
def mixed_tree(tmp_path):
    (tmp_path / 'a.py').write_text(PY)
    (tmp_path / 'b.js').write_text('function h() { return 1 }\n')
    (tmp_path / 'c.js').write_text('function i() { return 2 }\n')
    (tmp_path / 'd.go').write_text('package p\n')
    return tmp_path


@pytest.fixture
def python_tree(tmp_path):
    (tmp_path / 'a.py').write_text(PY)
    return tmp_path


def test_registry_declares_the_known_python_only_features():
    assert {'dict-heatmap', 'dict-schemas', 'reveal-type', 'rule-T006'} <= set(PYTHON_ONLY_FEATURES)


def test_python_profile_has_no_unavailable_features_but_others_list_them():
    assert get_capability_for_extension('.py').unsupported_features() == []
    assert get_capability_for_extension('.kt').unsupported_features() == sorted(PYTHON_ONLY_FEATURES)


def test_warning_names_the_languages_that_were_not_analyzed(mixed_tree):
    warning = python_only_warning('dict-heatmap', mixed_tree)
    assert warning['code'] == W_CAP_PYTHON_ONLY
    assert '3 file(s)' in warning['message']
    assert 'javascript (2)' in warning['message'] and 'go (1)' in warning['message']
    assert 'show=dict-heatmap' in warning['message']


def test_no_warning_for_an_all_python_tree_or_a_missing_path(python_tree, tmp_path):
    assert python_only_warning('dict-heatmap', python_tree) is None
    assert python_only_warning('dict-heatmap', tmp_path / 'does-not-exist') is None


@pytest.mark.parametrize('mode', ['dict-heatmap', 'dict-schemas'])
def test_dict_modes_carry_the_warning_in_result_meta(mixed_tree, mode):
    result = AstAdapter(str(mixed_tree), f'show={mode}').get_structure()
    assert [w['code'] for w in result['meta']['warnings']] == [W_CAP_PYTHON_ONLY]


def test_python_only_tree_result_has_no_warnings(python_tree):
    result = AstAdapter(str(python_tree), 'show=dict-heatmap').get_structure()
    assert result['meta']['warnings'] == []


def test_reveal_type_warns_on_mixed_tree(mixed_tree):
    result = AstAdapter(str(mixed_tree), 'reveal_type=cfg').get_structure()
    assert [w['code'] for w in result['meta']['warnings']] == [W_CAP_PYTHON_ONLY]


def test_text_renderer_prints_the_warning(mixed_tree, capsys):
    result = AstAdapter(str(mixed_tree), 'show=dict-heatmap').get_structure()
    _render_dict_heatmap(result, 'text')
    assert 'W-CAP-1' in capsys.readouterr().out
