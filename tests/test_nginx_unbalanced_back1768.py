"""BACK-1768: an nginx config whose braces do not balance states reduced trust."""
import pytest

from reveal.analyzers.nginx import NginxAnalyzer


def _meta(tmp_path, text):
    p = tmp_path / 'x.conf'
    p.write_text(text, encoding='utf-8')
    return NginxAnalyzer(str(p)).get_structure()['meta']


@pytest.mark.parametrize('text', [
    'server {\n listen 80;\n',            # unterminated block
    'server {\n listen 80;\n}\n}\n',      # extra closing brace
])
def test_unbalanced_config_lowers_confidence_and_warns(tmp_path, text):
    meta = _meta(tmp_path, text)
    assert meta['confidence'] <= 0.5
    assert [w['code'] for w in meta['warnings']] == ['unbalanced_braces']


def test_balanced_config_keeps_full_confidence(tmp_path):
    meta = _meta(tmp_path, 'server {\n listen 80;\n # } in a comment\n}\n')
    assert meta['confidence'] == 1.0
    assert not meta['warnings']
