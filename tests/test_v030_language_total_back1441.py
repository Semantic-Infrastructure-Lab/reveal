"""V030 checks the AGENT_HELP.md language total it claims to check (BACK-1441).

V030's pattern required "Programming Languages (N total"; 2eaf0d31 reworded the heading
to "(N languages and file formats in total", after which V030 matched nothing and
reported a clean result. A zero needs a positive control: these tests prove V030
finds the real heading and flags a wrong number in it.
"""
import re
import shutil
from pathlib import Path

import pytest

from reveal.rules.validation import V030 as v030_module
from reveal.rules.validation.V030 import V030

ROOT = Path(__file__).resolve().parent.parent
AGENT_HELP = ROOT / 'reveal' / 'docs' / 'AGENT_HELP.md'
OLD_PATTERN = re.compile(r'Programming Languages\s*\((\d+)\+?\s*total\b', re.IGNORECASE)


def _main_body_count_lines():
    lines = []
    for line in AGENT_HELP.read_text(encoding='utf-8').split('\n'):
        if V030._CHANGELOG_HEADING.match(line):
            break
        if re.search(r'Programming Languages\s*\(\s*\d', line, re.IGNORECASE):
            lines.append(line)
    return lines


def _matches(line):
    return any(pattern.search(line) for pattern, _metric in V030._TOTAL_PATTERNS)


def test_every_numbered_language_heading_is_checked():
    lines = _main_body_count_lines()
    assert lines, 'AGENT_HELP.md main body has no numbered Programming Languages heading'
    assert all(_matches(line) for line in lines), lines


def test_old_pattern_missed_the_current_heading():
    """Negative control: the pre-fix pattern is blind to today's wording."""
    assert not any(OLD_PATTERN.search(line) for line in _main_body_count_lines())


def _tree_with_claim(tmp_path, claimed):
    docs = tmp_path / 'reveal' / 'docs'
    docs.mkdir(parents=True)
    text = AGENT_HELP.read_text(encoding='utf-8')
    text = re.sub(r'(Programming Languages\s*\()\d+', rf'\g<1>{claimed}', text, count=1)
    (docs / 'AGENT_HELP.md').write_text(text, encoding='utf-8')
    return tmp_path / 'reveal'


@pytest.fixture
def actual():
    count = V030()._count_supported_languages()
    assert count
    return count


def test_wrong_total_is_flagged(monkeypatch, tmp_path, actual):
    monkeypatch.setattr(v030_module, 'find_reveal_root', lambda: _tree_with_claim(tmp_path, actual + 7))
    detections = V030().check('reveal://', None, '')
    assert len(detections) == 1
    assert f'claims {actual + 7}, actual {actual}' in detections[0].message


def test_right_total_is_clean(monkeypatch, tmp_path, actual):
    monkeypatch.setattr(v030_module, 'find_reveal_root', lambda: _tree_with_claim(tmp_path, actual))
    assert V030().check('reveal://', None, '') == []


def test_real_doc_is_clean():
    assert V030().check('reveal://', None, '') == []
