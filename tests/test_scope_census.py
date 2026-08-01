"""Tests for ScopeCensus / census_for_path / tally_files_by_language and
capabilities.capability_tiers_for (BACK-884).

Unlike LanguageCoverage (only asks "is the dominant language supported"),
ScopeCensus discloses the full per-language file breakdown for commands with
no restricted supported-language set (overview/architecture/check), plus
(where known) counts of files excluded before analysis began.
"""

import reveal.analyzers  # noqa: F401 — ensure code-extension registry is populated
from pathlib import Path

from reveal.utils.path_utils import (
    ScopeCensus,
    census_for_path,
    tally_files_by_language,
)
from reveal.capabilities import capability_tiers_for


def _write(root: Path, rel: str, text: str = 'x\n') -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class TestCensusForPath:
    def test_per_language_breakdown(self, tmp_path):
        for i in range(3):
            _write(tmp_path, f'src/mod{i}.py')
        for i in range(2):
            _write(tmp_path, f'src/mod{i}.lua')
        census = census_for_path(tmp_path)
        assert census.per_language == {'python': 3, 'lua': 2}
        assert census.total_code_files == 5

    def test_data_and_markup_excluded(self, tmp_path):
        _write(tmp_path, 'a.py')
        _write(tmp_path, 'README.md')
        _write(tmp_path, 'data.json')
        census = census_for_path(tmp_path)
        assert census.per_language == {'python': 1}

    def test_skip_dirs_honored_like_assess_language_coverage(self, tmp_path):
        # Same is_skippable_dir context-sensitivity as BACK-887: a real
        # source dir literally named 'env' is not undercounted.
        _write(tmp_path, 'env/main.java')
        census = census_for_path(tmp_path)
        assert census.per_language == {'java': 1}

    def test_build_output_dir_still_skipped(self, tmp_path):
        # No source file directly at build/'s own top level -> still skipped.
        _write(tmp_path, 'build/lib/generated.py')
        _write(tmp_path, 'src/real.py')
        census = census_for_path(tmp_path)
        assert census.per_language == {'python': 1}

    def test_empty_tree(self, tmp_path):
        census = census_for_path(tmp_path)
        assert census.per_language == {}
        assert census.total_code_files == 0

    def test_gitignore_and_no_analyzer_default_to_zero(self, tmp_path):
        # census_for_path walks directly — it has no gitignore/analyzer
        # visibility, unlike check's FileCollectionResult-derived census.
        _write(tmp_path, 'a.py')
        census = census_for_path(tmp_path)
        assert census.skipped_gitignore == 0
        assert census.skipped_no_analyzer == 0
        assert census.skipped_dirs == 0


class TestTallyFilesByLanguage:
    def test_buckets_by_language_with_representative_extension(self, tmp_path):
        _write(tmp_path, 'a.py')
        _write(tmp_path, 'b.py')
        _write(tmp_path, 'c.rs')
        files = [tmp_path / 'a.py', tmp_path / 'b.py', tmp_path / 'c.rs']
        counts = tally_files_by_language(files)
        assert counts == {
            'python': {'count': 2, 'ext': '.py'},
            'rust': {'count': 1, 'ext': '.rs'},
        }

    def test_ignores_files_with_no_registered_language(self, tmp_path):
        _write(tmp_path, 'notes.txt')
        counts = tally_files_by_language([tmp_path / 'notes.txt'])
        assert counts == {}


class TestScopeCensusToScopeDict:
    def test_shape_without_capability_tiers(self):
        census = ScopeCensus(
            per_language={'python': 3, 'lua': 2},
            skipped_gitignore=1,
            skipped_no_analyzer=4,
            skipped_dirs=2,
        )
        d = census.to_scope_dict()
        assert d == {
            'total_code_files': 5,
            'languages': [
                {'language': 'Python', 'files': 3},
                {'language': 'Lua', 'files': 2},
            ],
            'skipped_gitignore': 1,
            'skipped_no_analyzer': 4,
            'skipped_dirs': 2,
        }

    def test_sorted_by_count_descending_then_name(self):
        census = ScopeCensus(per_language={'lua': 1, 'python': 5, 'go': 1})
        d = census.to_scope_dict()
        names = [entry['language'] for entry in d['languages']]
        assert names == ['Python', 'Go', 'Lua']

    def test_capability_tier_joined_when_provided(self):
        census = ScopeCensus(
            per_language={'python': 1},
            language_extensions={'python': '.py'},
        )
        d = census.to_scope_dict(capability_tiers={'python': 'tier1_verified'})
        assert d['languages'][0]['capability_tier'] == 'tier1_verified'

    def test_capability_tier_key_absent_when_not_provided(self):
        census = ScopeCensus(per_language={'python': 1})
        d = census.to_scope_dict()
        assert 'capability_tier' not in d['languages'][0]

    def test_unknown_language_defaults_to_unknown_tier(self):
        census = ScopeCensus(
            per_language={'cobol': 1},
            language_extensions={'cobol': '.cbl'},
        )
        d = census.to_scope_dict(capability_tiers={})
        assert d['languages'][0]['capability_tier'] == 'unknown'


class TestCapabilityTiersFor:
    def test_known_extension_resolves_a_real_tier(self):
        tiers = capability_tiers_for({'python': '.py'})
        assert tiers['python'] not in (None, '')

    def test_unregistered_extension_maps_to_unknown(self):
        tiers = capability_tiers_for({'mystery': '.zzz-not-a-real-ext'})
        assert tiers['mystery'] == 'unknown'

    def test_empty_input_returns_empty(self):
        assert capability_tiers_for({}) == {}
