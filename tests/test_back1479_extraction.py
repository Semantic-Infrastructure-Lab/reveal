"""BACK-1479 by-name extraction leftovers: INI section.key, proto nested path, CSV names."""

import pytest

from reveal.display.element import _extract_by_syntax, _parse_element_syntax
from reveal.registry import get_analyzer

pytestmark = pytest.mark.component


def _extract(path, element):
    analyzer = get_analyzer(str(path))(str(path))
    return _extract_by_syntax(analyzer, element, _parse_element_syntax(element))


def test_ini_section_key_extracts_the_key_line(tmp_path):
    f = tmp_path / "a.ini"
    f.write_text("[db]\nhost=localhost\nport=5\n[web]\nport=80\n", encoding="utf-8")
    result = _extract(f, "web.port")
    assert (result["line_start"], result["line_end"], result["source"]) == (5, 5, "port=80")
    # same key name in another section resolves to that section's line
    assert _extract(f, "db.port")["line_start"] == 3


def test_ini_section_key_negative_controls(tmp_path):
    f = tmp_path / "a.ini"
    f.write_text("[db]\nhost=localhost\n", encoding="utf-8")
    assert _extract(f, "db.nope") is None
    assert _extract(f, "nodb.host") is None
    # a bare section still extracts as before
    assert _extract(f, "db")["line_start"] == 1


def test_ini_continuation_value_spans_its_lines(tmp_path):
    f = tmp_path / "a.ini"
    f.write_text("[s]\nk = one\n  two\nj = x\n", encoding="utf-8")
    result = _extract(f, "s.k")
    assert (result["line_start"], result["line_end"]) == (2, 3)
