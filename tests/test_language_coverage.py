"""Tests for assess_language_coverage / LanguageCoverage (BACK-518).

A language-limited command (surface/contracts support Python + TypeScript only)
pointed at a tree whose dominant language it can't analyze used to silently
build its whole report from whatever handful of supported-language files shared
the directory — e.g. `surface` on Kong (a 1,300-file Lua gateway with 15 stray
.py scripts) reported the surface of those 15 scripts as if it were the project.
The coverage assessment lets a command detect that and warn.
"""

import reveal.analyzers  # noqa: F401 — ensure code-extension registry is populated
from pathlib import Path

from reveal.utils.path_utils import assess_language_coverage, LanguageCoverage

# surface/contracts supported registry language keys
SUPPORTED = {'python', 'typescript', 'tsx'}


def _write(root: Path, rel: str, text: str = 'x\n') -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class TestShouldWarn:
    def test_stray_supported_minority_in_unsupported_tree_warns(self, tmp_path):
        # 20 .lua + 2 stray .py → dominant Lua, analyzed minority → warn.
        for i in range(20):
            _write(tmp_path, f'src/mod{i}.lua')
        _write(tmp_path, 'scripts/build.py')
        _write(tmp_path, 'scripts/gen.py')

        cov = assess_language_coverage(tmp_path, SUPPORTED)
        assert cov.total_code_files == 22
        assert cov.analyzed_files == 2
        assert cov.dominant_language == 'Lua'
        assert cov.dominant_count == 20
        assert cov.dominant_supported is False
        assert cov.should_warn is True
        assert '2 of 22' in cov.warning_line('surface')
        assert 'Lua' in cov.warning_line('surface')

    def test_supported_majority_never_warns(self, tmp_path):
        # A real Python project with a couple stray .lua files: dominant is
        # Python (supported) → no false-positive warning.
        for i in range(20):
            _write(tmp_path, f'pkg/mod{i}.py')
        _write(tmp_path, 'vendor/plugin.lua')
        _write(tmp_path, 'vendor/other.lua')

        cov = assess_language_coverage(tmp_path, SUPPORTED)
        assert cov.dominant_language == 'Python'
        assert cov.dominant_supported is True
        assert cov.should_warn is False
        assert cov.warning_line('surface') == ''

    def test_fully_unsupported_tree_warns(self, tmp_path):
        # Zero supported files at all (Scala/Dart-shaped corpus) → warn.
        for i in range(10):
            _write(tmp_path, f'app/M{i}.scala')
        cov = assess_language_coverage(tmp_path, SUPPORTED)
        assert cov.analyzed_files == 0
        assert cov.dominant_language == 'Scala'
        assert cov.should_warn is True

    def test_empty_tree_does_not_warn(self, tmp_path):
        _write(tmp_path, 'README.md', '# hi\n')  # non-code file
        cov = assess_language_coverage(tmp_path, SUPPORTED)
        assert cov.total_code_files == 0
        assert cov.should_warn is False

    def test_tie_dominant_supported_wins_no_warn(self, tmp_path):
        # Equal counts where a supported language is (at least) tied for dominant
        # must not warn: analyzed_files (10) is not < dominant_count (10).
        for i in range(10):
            _write(tmp_path, f'py/m{i}.py')
            _write(tmp_path, f'lua/m{i}.lua')
        cov = assess_language_coverage(tmp_path, SUPPORTED)
        # analyzed (10 py) == dominant_count (10) → strict-less-than is False.
        assert cov.should_warn is False

    def test_data_and_markup_excluded_from_denominator(self, tmp_path):
        # 5 .py code files + a pile of json/yaml/md must count as 5 code files,
        # not be diluted by data/markup (which would suppress or distort ratio).
        for i in range(5):
            _write(tmp_path, f'app/m{i}.py')
        for i in range(50):
            _write(tmp_path, f'data/d{i}.json', '{}\n')
            _write(tmp_path, f'docs/d{i}.md', '# t\n')
        cov = assess_language_coverage(tmp_path, SUPPORTED)
        assert cov.total_code_files == 5
        assert cov.dominant_language == 'Python'
        assert cov.should_warn is False


class TestSingleFile:
    def test_single_supported_file_no_warn(self, tmp_path):
        f = tmp_path / 'a.py'
        f.write_text('x = 1\n')
        cov = assess_language_coverage(f, SUPPORTED)
        assert cov.total_code_files == 1
        assert cov.analyzed_files == 1
        assert cov.should_warn is False

    def test_single_unsupported_file_warns(self, tmp_path):
        f = tmp_path / 'a.lua'
        f.write_text('return {}\n')
        cov = assess_language_coverage(f, SUPPORTED)
        assert cov.total_code_files == 1
        assert cov.analyzed_files == 0
        assert cov.dominant_language == 'Lua'
        assert cov.should_warn is True


class TestSkipDirs:
    def test_hidden_and_skip_dirs_not_counted(self, tmp_path):
        _write(tmp_path, 'src/main.lua')
        _write(tmp_path, '.git/hooks/pre.py')          # hidden dir
        _write(tmp_path, 'node_modules/dep/index.py')  # SKIP_DIRECTORIES
        cov = assess_language_coverage(tmp_path, SUPPORTED)
        # Only src/main.lua counts; the .py files under skipped dirs are ignored.
        assert cov.total_code_files == 1
        assert cov.analyzed_files == 0
