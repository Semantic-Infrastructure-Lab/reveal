"""Tests for I008: imported package not declared in the manifest (BACK-1191)."""

from __future__ import annotations

from pathlib import Path

import pytest

from reveal.rules.imports.I008 import I008

# BACK-1149: component-layer test -- single rule/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


class TestI008Python:
    def test_undeclared_import_flagged(self, tmp_path):
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["requests"]\n'
        ))
        app = _write(tmp_path / 'app.py', 'import requests\nimport numpy\n')

        result = I008().check(str(app), None, '')

        assert len(result) == 1
        assert 'numpy' in result[0].context
        assert result[0].line == 2
        assert result[0].rule_code == 'I008'

    def test_declared_import_not_flagged(self, tmp_path):
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["requests"]\n'
        ))
        app = _write(tmp_path / 'app.py', 'import requests\n')

        result = I008().check(str(app), None, '')

        assert result == []

    def test_stdlib_import_not_flagged(self, tmp_path):
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["requests"]\n'
        ))
        app = _write(tmp_path / 'app.py', 'import os\nimport json\nimport requests\n')

        result = I008().check(str(app), None, '')

        assert result == []

    def test_local_package_import_not_flagged(self, tmp_path):
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["requests"]\n'
        ))
        _write(tmp_path / 'mypkg' / '__init__.py', '')
        app = _write(tmp_path / 'app.py', 'import mypkg\nimport requests\n')

        result = I008().check(str(app), None, '')

        assert result == []

    def test_known_alias_not_flagged(self, tmp_path):
        # Pillow is imported as `PIL` -- a genuine name mismatch the
        # PY_IMPORT_TO_DIST_ALIASES table exists to prevent false-flagging.
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["Pillow"]\n'
        ))
        app = _write(tmp_path / 'app.py', 'from PIL import Image\n')

        result = I008().check(str(app), None, '')

        assert result == []

    def test_dnspython_alias_not_flagged(self, tmp_path):
        # Found live dogfooding this rule against reveal's own
        # pyproject.toml (BACK-1191) -- dnspython imports as `dns`.
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["dnspython"]\n'
        ))
        app = _write(tmp_path / 'app.py', 'import dns.resolver\n')

        result = I008().check(str(app), None, '')

        assert result == []

    def test_no_declared_dependencies_stays_silent(self, tmp_path):
        # Empty manifest inventory -- flagging every external import here
        # would be noise, not a finding (matches BACK-1189's honest-decline
        # design for is_intra_project_import's own None case).
        _write(tmp_path / 'pyproject.toml', '[project]\nname = "demo"\n')
        app = _write(tmp_path / 'app.py', 'import numpy\nimport pandas\n')

        result = I008().check(str(app), None, '')

        assert result == []

    def test_test_directory_conftest_sibling_import_not_flagged(self, tmp_path):
        # BACK-1191: pytest's `from conftest import X` sibling-import
        # convention (resolved via pytest's own rootdir sys.path
        # insertion) is invisible to local-package detection -- dogfooded
        # live on reveal's own ~950-file corpus, every test-dir finding was
        # this pattern. Test directories are skipped entirely rather than
        # false-flagged.
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["requests"]\n'
        ))
        test_file = _write(tmp_path / 'tests' / 'test_app.py', 'from conftest import fixture_x\n')

        result = I008().check(str(test_file), None, '')

        assert result == []

    def test_relative_import_not_flagged(self, tmp_path):
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["requests"]\n'
        ))
        _write(tmp_path / 'pkg' / '__init__.py', '')
        app = _write(tmp_path / 'pkg' / 'mod.py', 'from . import sibling\n')

        result = I008().check(str(app), None, '')

        assert result == []


class TestI008Rust:
    def test_undeclared_crate_flagged(self, tmp_path):
        _write(tmp_path / 'Cargo.toml', (
            '[package]\nname = "demo"\nversion = "0.1.0"\n'
            '[dependencies]\nserde = "1.0"\n'
        ))
        main = _write(tmp_path / 'src' / 'main.rs', (
            'use serde::Serialize;\nuse tokio::runtime::Runtime;\nfn main() {}\n'
        ))

        result = I008().check(str(main), None, '')

        assert len(result) == 1
        assert 'tokio' in result[0].context

    def test_std_crate_not_flagged(self, tmp_path):
        _write(tmp_path / 'Cargo.toml', (
            '[package]\nname = "demo"\nversion = "0.1.0"\n'
            '[dependencies]\nserde = "1.0"\n'
        ))
        main = _write(tmp_path / 'src' / 'main.rs', (
            'use std::collections::HashMap;\nuse serde::Serialize;\nfn main() {}\n'
        ))

        result = I008().check(str(main), None, '')

        assert result == []

    def test_declared_crate_not_flagged(self, tmp_path):
        _write(tmp_path / 'Cargo.toml', (
            '[package]\nname = "demo"\nversion = "0.1.0"\n'
            '[dependencies]\nserde = "1.0"\n'
        ))
        main = _write(tmp_path / 'src' / 'main.rs', 'use serde::Serialize;\nfn main() {}\n')

        result = I008().check(str(main), None, '')

        assert result == []

    def test_no_dependencies_table_stays_silent(self, tmp_path):
        _write(tmp_path / 'Cargo.toml', '[package]\nname = "demo"\nversion = "0.1.0"\n')
        main = _write(tmp_path / 'src' / 'main.rs', 'use tokio::runtime::Runtime;\nfn main() {}\n')

        result = I008().check(str(main), None, '')

        assert result == []


def test_i008_file_patterns_are_reasonable():
    assert I008.code == 'I008'
    assert set(I008.file_patterns) == {'.py', '.rs'}
