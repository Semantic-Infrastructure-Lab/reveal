"""BACK-1430: M101 must not say 'too large' for a file under its own limit.

Two defects shared one symptom: the 500-1000 line warning tier carried the
"File is too large" message although the rule's limit is 1,000 lines, and a
file of exactly 1,000 lines ending in a newline was counted as 1,001
(``content.count('\\n') + 1`` counts the empty tail after the last newline).
"""

import pytest

from reveal.rules.base import Severity
from reveal.rules.maintainability.M101 import M101

pytestmark = pytest.mark.component


def _check(tmp_path, n_lines, trailing_newline=True):
    text = "\n".join(f"line{i}" for i in range(n_lines)) + ("\n" if trailing_newline else "")
    path = tmp_path / "f.txt"
    path.write_text(text, encoding='utf-8')
    return M101().check(str(path), None, text)


def test_warning_tier_does_not_claim_too_large(tmp_path):
    (det,) = _check(tmp_path, 600)
    assert det.severity == Severity.MEDIUM
    assert "too large" not in det.message.lower()
    assert "600 lines" in det.message


def test_exactly_at_limit_with_trailing_newline_is_not_an_error(tmp_path):
    (det,) = _check(tmp_path, 1000)
    assert det.severity == Severity.MEDIUM
    assert "too large" not in det.message.lower()
    assert "1,000 lines" in det.message


def test_exactly_500_lines_with_trailing_newline_is_clean(tmp_path):
    assert _check(tmp_path, 500) == []


def test_over_the_limit_is_still_too_large(tmp_path):
    """Negative control: the error tier keeps its wording and severity."""
    (det,) = _check(tmp_path, 1001, trailing_newline=False)
    assert det.severity == Severity.HIGH
    assert "too large" in det.message.lower()
    assert "1,001 lines" in det.message


def test_over_the_limit_with_trailing_newline_counts_real_lines(tmp_path):
    (det,) = _check(tmp_path, 1001)
    assert det.severity == Severity.HIGH
    assert "1,001 lines" in det.message
