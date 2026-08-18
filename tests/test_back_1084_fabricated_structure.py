"""Regression tests for BACK-1084: `reveal <file>` fabricates plausible
structure for an unparseable file with no error signal.

Tree-sitter's error-tolerant parser recovers from a plain syntax error and
still returns structure -- e.g. `def foo(:` parses to a function named
`foo` with a garbled signature, with nothing in the output distinguishing
it from a genuinely clean file.

Two distinct recovery shapes matter here, and this is what has_parse_errors()
(built for BACK-1082, an explicit ERROR-node check) gets wrong for this
case: `def foo(:` recovers as a well-typed subtree with a MISSING token
spliced in (`(parameters (MISSING ")"))`), no ERROR node anywhere in the
tree -- confirmed live via `tree.root_node().to_sexp()`. The ERROR-node-only
check silently returns False for this exact BACK-1084 repro.

The fix adds a separate, wider check -- `_has_recovery_artifacts()`, using
tree-sitter's own recursive `has_error()` -- used only by get_structure()'s
additive `_has_errors` disclosure flag, NOT by has_parse_errors() itself.
`has_error()` also fires on a confirmed-benign grammar quirk (a C/C++ file
consisting only of #include lines trips a trailing MISSING token in
tree-sitter-c with nothing actually wrong), which would have been a real
regression if wired into has_parse_errors() -- imports/base.py's
parse_failed guard would then silently drop real #include results. Keeping
the two checks separate means get_structure() gets the wider, occasionally
over-cautious signal appropriate for an advisory flag, while
imports/base.py keeps the narrower, tested-stable ERROR-node check where a
false positive means dropping real results.
"""

from pathlib import Path

from reveal.analyzers.python import PythonAnalyzer


def _write_py(tmp_path: Path, name: str, code: str) -> Path:
    p = tmp_path / name
    p.write_text(code, encoding="utf-8")
    return p


class TestRecoveryArtifactsCatchesMissingTokenRecovery:
    """Direct coverage of the new _has_recovery_artifacts() check."""

    def test_unclosed_paren_flagged_even_with_no_error_node(self, tmp_path):
        f = _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        analyzer = PythonAnalyzer(str(f))

        # This is the actual BACK-1084 failure mode: no ERROR-kind node in
        # the recovered tree, only a MISSING token -- so has_parse_errors()
        # (ERROR-node-only) misses it; _has_recovery_artifacts() must not.
        assert analyzer.has_parse_errors() is False
        assert analyzer._has_recovery_artifacts() is True

    def test_clean_file_not_flagged(self, tmp_path):
        f = _write_py(tmp_path, "clean.py", "def foo():\n    pass\n")
        analyzer = PythonAnalyzer(str(f))

        assert analyzer._has_recovery_artifacts() is False

    def test_explicit_error_node_still_caught(self, tmp_path):
        """Sanity: the original BACK-1082 ERROR-node shape is still caught
        by the wider check too (has_error() is a superset)."""
        f = _write_py(tmp_path, "broken2.py", "import os\nimport sys\ndef f(\n")
        analyzer = PythonAnalyzer(str(f))

        assert analyzer.has_parse_errors() is True
        assert analyzer._has_recovery_artifacts() is True


class TestGetStructureSurfacesHasErrors:
    """End-to-end: get_structure() must additively flag a partial/recovered
    parse so a JSON consumer isn't handed fabricated structure with no way
    to tell it apart from a confidently-clean result."""

    def test_broken_file_structure_carries_has_errors_flag(self, tmp_path):
        f = _write_py(tmp_path, "broken.py", "def foo(:\n    pass\n")
        analyzer = PythonAnalyzer(str(f))

        structure = analyzer.get_structure()

        assert structure.get("_has_errors") is True
        # And the fabricated-looking function is still there -- this is an
        # additive signal, not a behavior change to what's returned.
        assert structure["functions"][0]["name"] == "foo"

    def test_clean_file_structure_has_no_error_flag(self, tmp_path):
        f = _write_py(tmp_path, "clean.py", "def foo():\n    pass\n")
        analyzer = PythonAnalyzer(str(f))

        structure = analyzer.get_structure()

        assert "_has_errors" not in structure


class TestHasParseErrorsUnaffectedByWiderCheck:
    """has_parse_errors() (the imports/base.py consumer) must NOT pick up
    the wider _has_recovery_artifacts() detection -- confirmed live that
    an include-only C file trips has_error() on a benign trailing MISSING
    token in tree-sitter-c's grammar, which must not make I001-style
    consumers drop real #include results (tests/test_imports_generic.py)."""

    def test_include_only_c_file_not_flagged_by_narrow_check(self, tmp_path):
        from reveal.analyzers.c import CAnalyzer

        f = tmp_path / "headers.c"
        f.write_text('#include <stdio.h>\n#include "local.h"\n', encoding="utf-8")
        analyzer = CAnalyzer(str(f))

        # The wider check DOES flag this (a real, if benign, MISSING token)
        assert analyzer._has_recovery_artifacts() is True
        # But the narrow check imports/base.py relies on must stay clean.
        assert analyzer.has_parse_errors() is False
