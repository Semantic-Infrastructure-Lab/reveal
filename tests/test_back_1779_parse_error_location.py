"""BACK-1779: "did not parse cleanly" names where the parser first lost its place.

Real C firmware (vendor typedef casts, `__attribute__((fallthrough));` statements,
`#else` straddling an `if`) trips tree-sitter-c; the warning used to say only that
results may be wrong, leaving the user to bisect a 1,000-line file.
"""
import json
import subprocess
import sys

import pytest

FALLTHROUGH_C = (
    "int a;\n\n"
    "int f(int x) {\n"
    "    switch (x) {\n"
    "    case 1:\n"
    "        x++;\n"
    "        __attribute__((fallthrough));\n"   # line 7, column 9
    "    case 2:\n"
    "        x--;\n"
    "    }\n"
    "    return x;\n"
    "}\n"
)
BROKEN_JS = "const a = 1;\nfunction f( {\n  return 1;\n}\n"


def _check(path, *args):
    return subprocess.run(
        [sys.executable, "-m", "reveal.main", "check", str(path), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )


@pytest.fixture
def c_file(tmp_path):
    p = tmp_path / "fall.c"
    p.write_text(FALLTHROUGH_C, encoding="utf-8")
    return p


def test_analyzer_reports_first_error_position(c_file):
    from reveal.registry import get_analyzer
    analyzer = get_analyzer(str(c_file), allow_fallback=False)(str(c_file))
    assert analyzer.first_parse_error_position() == (7, 9)


def test_clean_file_has_no_error_position(tmp_path):
    from reveal.registry import get_analyzer
    p = tmp_path / "ok.c"
    p.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    assert get_analyzer(str(p), allow_fallback=False)(str(p)).first_parse_error_position() is None


def test_single_file_text_names_the_location(c_file):
    out = _check(c_file).stdout
    assert "did not parse cleanly (first error at line 7:9)" in out


def test_single_file_json_warning_names_the_location(c_file):
    doc = json.loads(_check(c_file, "--format", "json").stdout)
    text = json.dumps(doc)
    assert "first error at line 7:9" in text


def test_directory_check_names_the_location(c_file):
    out = _check(c_file.parent).stdout
    assert "fall.c" in out and "first error at line 7:9" in out


def test_mcp_check_names_the_location(c_file):
    from reveal.mcp_server import reveal_check
    assert "first error at line 7:9" in reveal_check(str(c_file))


def test_other_tree_sitter_languages_are_located_too(tmp_path):
    p = tmp_path / "broken.js"
    p.write_text(BROKEN_JS, encoding="utf-8")
    assert "first error at line 2:" in _check(p).stdout
