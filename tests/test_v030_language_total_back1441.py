"""V030 gates the README headline language count against `reveal --languages` (BACK-1441).

README.md carries the one hand-written language total; other docs point at
`reveal --languages`. V030 once matched nothing after a reword and reported clean, so these
tests are the positive control (the real headline is found and checked) and the negative
controls (a wrong headline, an underclaim, and a missing headline all fail loudly).
"""
import re
from pathlib import Path

import pytest

from reveal.rules.validation import V030 as v030_module
from reveal.rules.validation.V030 import V030

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / 'README.md'


def _tree_with_readme(tmp_path, transform):
    (tmp_path / 'reveal').mkdir()
    text = transform(README.read_text(encoding='utf-8'))
    (tmp_path / 'README.md').write_text(text, encoding='utf-8')
    return tmp_path / 'reveal'


def _check(monkeypatch, tmp_path, transform):
    monkeypatch.setattr(v030_module, 'find_reveal_root',
                        lambda: _tree_with_readme(tmp_path, transform))
    return V030().check('reveal://', None, '')


@pytest.fixture
def actual():
    count = V030()._count_supported_languages()
    assert count
    return count


def test_readme_has_exactly_one_headline_claim():
    text = README.read_text(encoding='utf-8')
    assert len(V030._CLAIM.findall(text)) == 1


def test_real_readme_is_clean():
    assert V030().check('reveal://', None, '') == []


def test_right_total_is_clean(monkeypatch, tmp_path, actual):
    assert _check(monkeypatch, tmp_path,
                  lambda t: V030._CLAIM.sub(f'{actual} languages and file formats', t)) == []


@pytest.mark.parametrize('delta', [7, -3])
def test_wrong_total_is_flagged(monkeypatch, tmp_path, actual, delta):
    claimed = actual + delta
    detections = _check(monkeypatch, tmp_path,
                        lambda t: V030._CLAIM.sub(f'{claimed} languages and file formats', t))
    assert len(detections) == 1
    assert f'claims {claimed}, actual {actual}' in detections[0].message
    assert detections[0].file_path == 'README.md'


def test_missing_headline_fails_loudly(monkeypatch, tmp_path):
    detections = _check(monkeypatch, tmp_path,
                        lambda t: re.sub(r'\d+ languages and file formats', 'many languages', t))
    assert len(detections) == 1
    assert 'not found' in detections[0].message


def test_other_docs_carry_no_language_total():
    """The pointer wording is what keeps the number single-homed."""
    pattern = re.compile(r'(?<![\w.-])\d+\+?\s+(?:programming\s+)?languages(?: and file formats)?\b', re.I)
    docs = [ROOT / 'reveal' / 'docs' / n for n in
            ('AGENT_HELP.md', 'QUICK_START.md', 'WHY_REVEAL.md', 'adapters/AST_ADAPTER_GUIDE.md')]
    docs.append(ROOT / 'STABILITY.md')
    for doc in docs:
        text = doc.read_text(encoding='utf-8')
        text = text.split('## What Changed in This Guide', 1)[0]
        # per-feature counts like "11 languages: Python, ..." are not totals
        hits = [m.group(0) for m in pattern.finditer(text)
                if not text[m.end():m.end() + 1] == ':']
        assert hits == [], (doc.name, hits)
