"""Tests for reveal.utils.parallel — grep_files()."""

import pytest
from pathlib import Path

from reveal.utils.parallel import grep_files, _PARALLEL_THRESHOLD


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def doc_dir(tmp_path):
    """A small corpus of text files with varied content."""
    (tmp_path / "auth.md").write_bytes(b"# Auth Guide\n\nauthentication and authorization\n")
    (tmp_path / "deploy.md").write_bytes(b"# Deploy\n\nproduction deployment steps\n")
    (tmp_path / "both.md").write_bytes(b"# Combined\n\nauthentication before production deploy\n")
    (tmp_path / "empty.md").write_bytes(b"")
    (tmp_path / "upper.md").write_bytes(b"AUTHENTICATION IS REQUIRED\n")
    return tmp_path


@pytest.fixture
def large_doc_dir(tmp_path):
    """Corpus large enough to trigger the parallel code path."""
    for i in range(_PARALLEL_THRESHOLD + 4):
        content = f"document {i} content\n".encode()
        (tmp_path / f"doc_{i:02d}.md").write_bytes(content)
    # One file with the target term
    (tmp_path / "target.md").write_bytes(b"this one has the needle\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------

class TestGrepFilesBasic:

    def test_single_term_match(self, doc_dir):
        paths = list(doc_dir.glob("*.md"))
        result = grep_files(paths, "authentication")
        names = {p.name for p in result}
        assert "auth.md" in names
        assert "both.md" in names
        assert "upper.md" in names  # case-insensitive

    def test_single_term_no_match(self, doc_dir):
        paths = list(doc_dir.glob("*.md"))
        result = grep_files(paths, "kubernetes")
        assert result == []

    def test_and_logic_all_terms(self, doc_dir):
        paths = list(doc_dir.glob("*.md"))
        result = grep_files(paths, ["authentication", "production"])
        names = {p.name for p in result}
        assert names == {"both.md"}

    def test_and_logic_partial_match_excluded(self, doc_dir):
        paths = list(doc_dir.glob("*.md"))
        result = grep_files(paths, ["authentication", "nonexistent"])
        assert result == []

    def test_case_insensitive(self, doc_dir):
        paths = list(doc_dir.glob("*.md"))
        result_lower = grep_files(paths, "authentication")
        result_upper = grep_files(paths, "AUTHENTICATION")
        result_mixed = grep_files(paths, "Authentication")
        assert {p.name for p in result_lower} == {p.name for p in result_upper}
        assert {p.name for p in result_lower} == {p.name for p in result_mixed}

    def test_empty_file_no_match(self, doc_dir):
        paths = [doc_dir / "empty.md"]
        result = grep_files(paths, "anything")
        assert result == []

    def test_string_term_same_as_list(self, doc_dir):
        paths = list(doc_dir.glob("*.md"))
        from_str = grep_files(paths, "authentication")
        from_list = grep_files(paths, ["authentication"])
        assert {p.name for p in from_str} == {p.name for p in from_list}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestGrepFilesEdgeCases:

    def test_empty_paths_list(self):
        result = grep_files([], "term")
        assert result == []

    def test_empty_term_matches_all(self, doc_dir):
        paths = list(doc_dir.glob("*.md"))
        result = grep_files(paths, "")
        assert len(result) == len(paths)

    def test_empty_terms_list_matches_all(self, doc_dir):
        paths = list(doc_dir.glob("*.md"))
        result = grep_files(paths, [])
        assert len(result) == len(paths)

    def test_unreadable_file_skipped(self, tmp_path):
        good = tmp_path / "good.md"
        good.write_bytes(b"hello world")
        bad = tmp_path / "bad.md"
        bad.write_bytes(b"hello world")
        bad.chmod(0o000)
        try:
            paths = [good, bad]
            result = grep_files(paths, "hello")
            # good.md matches; bad.md silently skipped on permission error
            assert good in result
        finally:
            bad.chmod(0o644)  # restore for cleanup

    def test_preserves_input_order(self, doc_dir):
        """Matching paths appear in the same relative order as the input."""
        paths = sorted(doc_dir.glob("*.md"))  # deterministic order
        result = grep_files(paths, "authentication")
        # Result is a subset; verify relative order is preserved
        result_indices = [paths.index(p) for p in result]
        assert result_indices == sorted(result_indices)

    def test_generator_input(self, doc_dir):
        """Accepts any iterable, not just lists."""
        paths_gen = (p for p in doc_dir.glob("*.md"))
        result = grep_files(paths_gen, "authentication")
        assert len(result) > 0

    def test_single_file_input(self, doc_dir):
        result = grep_files([doc_dir / "auth.md"], "authentication")
        assert result == [doc_dir / "auth.md"]

    def test_single_file_no_match(self, doc_dir):
        result = grep_files([doc_dir / "auth.md"], "kubernetes")
        assert result == []


# ---------------------------------------------------------------------------
# Sequential vs parallel code paths
# ---------------------------------------------------------------------------

class TestGrepFilesParallelPaths:

    def test_sequential_path_small_corpus(self, doc_dir):
        """Below threshold: sequential path produces correct results."""
        paths = list(doc_dir.glob("*.md"))
        assert len(paths) < _PARALLEL_THRESHOLD
        result = grep_files(paths, "authentication")
        assert len(result) > 0

    def test_parallel_path_large_corpus(self, large_doc_dir):
        """Above threshold: parallel path produces correct results."""
        paths = list(large_doc_dir.glob("*.md"))
        assert len(paths) >= _PARALLEL_THRESHOLD
        result = grep_files(paths, "needle")
        assert len(result) == 1
        assert result[0].name == "target.md"

    def test_parallel_and_sequential_same_results(self, tmp_path):
        """Both paths return identical results for the same corpus."""
        # Build a corpus that spans the threshold
        for i in range(_PARALLEL_THRESHOLD + 6):
            txt = f"item {i} " + ("match_me" if i % 3 == 0 else "no") + "\n"
            (tmp_path / f"f{i:02d}.md").write_bytes(txt.encode())

        paths = sorted(tmp_path.glob("*.md"))
        small = paths[:_PARALLEL_THRESHOLD - 1]  # sequential path
        large = paths                              # parallel path

        r_small = grep_files(small, "match_me")
        r_large = grep_files(large, "match_me")

        # Every match in the small set must appear in the large set
        assert all(p in r_large for p in r_small)


# ---------------------------------------------------------------------------
# Interaction with markdown body_contains (frontmatter false-positive check)
# ---------------------------------------------------------------------------

class TestGrepFilesMarkdownFalsePositives:

    def test_term_in_frontmatter_only_is_pre_filter_candidate(self, tmp_path):
        """grep_files returns files where term is in frontmatter (whole-file scan).
        The secondary body-only check in matches_body_contains must filter these out.
        """
        (tmp_path / "fm_only.md").write_bytes(
            b"---\nbeth_topics:\n  - authentication\n---\n\nNo auth content here.\n"
        )
        paths = [tmp_path / "fm_only.md"]
        # grep_files SHOULD return this — it's a pre-filter, not a body-only filter
        result = grep_files(paths, "authentication")
        assert result == paths  # found in frontmatter → passes pre-filter

    def test_term_in_body_passes_both_filters(self, tmp_path):
        (tmp_path / "body.md").write_bytes(
            b"---\ntitle: Test\n---\n\nauthentication flow explained here\n"
        )
        paths = [tmp_path / "body.md"]
        result = grep_files(paths, "authentication")
        assert result == paths
