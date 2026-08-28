"""Tests for reveal/analyzers/_capability_table.py (BACK-1093).

The shared per-(language, adapter, signal) registry that replaces two
independent, adapter-private trust mechanisms (depends://'s True/False/None
intra-project classifier, calls://'s per-language extraction-confidence
table) with one consultable surface.
"""

import pytest

from reveal.analyzers._capability_table import (
    calls_extraction_confidence,
    depends_intra_project_classification_supported,
)
from reveal.defaults import CALL_GRAPH_EXTRACTION_CONFIDENCE, CALL_GRAPH_DEFAULT_CONFIDENCE

# BACK-1149: exercises internal functions/modules directly, not CLI/MCP/network surface
pytestmark = pytest.mark.component


class TestCallsExtractionConfidence:
    """Thin delegation to defaults.CALL_GRAPH_EXTRACTION_CONFIDENCE -- must
    stay byte-identical to the raw table lookup (BACK-1198's measured
    figures), just reachable through one shared import."""

    def test_measured_language_matches_raw_table(self):
        assert calls_extraction_confidence('python') == CALL_GRAPH_EXTRACTION_CONFIDENCE['python']
        assert calls_extraction_confidence('go') == CALL_GRAPH_EXTRACTION_CONFIDENCE['go']

    def test_unmeasured_language_falls_back_to_default(self):
        assert calls_extraction_confidence('some-made-up-language') == CALL_GRAPH_DEFAULT_CONFIDENCE


class TestDependsIntraProjectClassificationSupported:
    """Derived (not hand-maintained) per-language capability: does this
    language's import extractor ever return real True/False from
    is_intra_project_import(), or does it always fall through to the base
    class's honest-but-uninformative None."""

    def test_python_is_supported(self):
        # python.py has a dedicated override.
        assert depends_intra_project_classification_supported('Python') is True

    def test_go_is_supported(self):
        # go.py has a dedicated override.
        assert depends_intra_project_classification_supported('Go') is True

    def test_csharp_is_supported(self):
        # generic.py's shared extractor with package_node_types set.
        assert depends_intra_project_classification_supported('C#') is True

    def test_swift_is_supported(self):
        # generic.py's shared extractor with module_dir_convention set.
        assert depends_intra_project_classification_supported('Swift') is True

    def test_ruby_is_not_supported(self):
        # generic.py's shared extractor, but Ruby's spec sets none of the
        # flags is_intra_project_import branches on -- always falls through
        # to None (BACK-1093's motivating gap).
        assert depends_intra_project_classification_supported('Ruby') is False

    def test_rust_is_not_supported(self):
        # rust.py subclasses LanguageExtractor directly, no override at all.
        assert depends_intra_project_classification_supported('Rust') is False

    def test_unknown_language_defaults_to_not_supported(self):
        # Conservative default for a language absent from the registry entirely
        # -- consistent with is_intra_project_import's own "don't guess" stance.
        assert depends_intra_project_classification_supported('Cobol') is False
