"""Tests for I007: declared dependency never imported anywhere (BACK-1191)."""

from __future__ import annotations

from pathlib import Path

import pytest

from reveal.rules.imports.I007 import I007

# BACK-1149: component-layer test -- single rule/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


class TestI007Python:
    def test_unused_dependency_flagged(self, tmp_path):
        _write(tmp_path / 'pyproject.toml', (
            '[project]\n'
            'name = "demo"\n'
            'dependencies = ["requests", "orjson"]\n'
        ))
        _write(tmp_path / 'app.py', 'import requests\n')

        result = I007().check(str(tmp_path / 'pyproject.toml'), None, '')

        names = {d.context.split(': ')[-1] for d in result}
        assert names == {'orjson'}
        assert result[0].rule_code == 'I007'

    def test_used_dependency_not_flagged(self, tmp_path):
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["requests"]\n'
        ))
        _write(tmp_path / 'app.py', 'import requests\n')

        result = I007().check(str(tmp_path / 'pyproject.toml'), None, '')

        assert result == []

    def test_dependency_used_via_known_alias_not_flagged(self, tmp_path):
        # PyYAML is imported as `yaml` -- a genuine name mismatch the
        # PY_DIST_TO_IMPORT_ALIASES table exists to prevent false-flagging.
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["PyYAML"]\n'
        ))
        _write(tmp_path / 'app.py', 'import yaml\n')

        result = I007().check(str(tmp_path / 'pyproject.toml'), None, '')

        assert result == []

    def test_no_declared_dependencies_stays_silent(self, tmp_path):
        _write(tmp_path / 'pyproject.toml', '[project]\nname = "demo"\n')
        _write(tmp_path / 'app.py', 'import os\n')

        result = I007().check(str(tmp_path / 'pyproject.toml'), None, '')

        assert result == []

    def test_requirements_txt_skipped_when_pyproject_present(self, tmp_path):
        # Both manifests declare the same unused dep -- must report once,
        # from pyproject.toml, not duplicate from requirements.txt too.
        _write(tmp_path / 'pyproject.toml', (
            '[project]\nname = "demo"\ndependencies = ["orjson"]\n'
        ))
        _write(tmp_path / 'requirements.txt', 'orjson\n')
        _write(tmp_path / 'app.py', 'import os\n')

        result = I007().check(str(tmp_path / 'requirements.txt'), None, '')

        assert result == []

    def test_requirements_txt_alone_flags_unused(self, tmp_path):
        _write(tmp_path / 'requirements.txt', 'orjson\nrequests\n')
        _write(tmp_path / 'app.py', 'import requests\n')

        result = I007().check(str(tmp_path / 'requirements.txt'), None, '')

        names = {d.context.split(': ')[-1] for d in result}
        assert names == {'orjson'}


class TestI007Rust:
    def test_unused_crate_flagged(self, tmp_path):
        _write(tmp_path / 'Cargo.toml', (
            '[package]\nname = "demo"\nversion = "0.1.0"\n'
            '[dependencies]\nserde = "1.0"\nrand = "0.8"\n'
        ))
        _write(tmp_path / 'src' / 'main.rs', 'use serde::Serialize;\nfn main() {}\n')

        result = I007().check(str(tmp_path / 'Cargo.toml'), None, '')

        names = {d.context.split(': ')[-1] for d in result}
        assert names == {'rand'}

    def test_used_crate_not_flagged(self, tmp_path):
        _write(tmp_path / 'Cargo.toml', (
            '[package]\nname = "demo"\nversion = "0.1.0"\n'
            '[dependencies]\nserde = "1.0"\n'
        ))
        _write(tmp_path / 'src' / 'main.rs', 'use serde::Serialize;\nfn main() {}\n')

        result = I007().check(str(tmp_path / 'Cargo.toml'), None, '')

        assert result == []

    def test_path_dependency_not_flagged_as_unused(self, tmp_path):
        # A `path = "..."` dependency is a workspace-local sibling crate,
        # not a real external dependency (_rust_crate_inventory classifies
        # it local) -- I007 must not report it as "declared but unused".
        _write(tmp_path / 'Cargo.toml', (
            '[package]\nname = "demo"\nversion = "0.1.0"\n'
            '[dependencies]\nmy_sibling = { path = "../my_sibling" }\n'
        ))
        _write(tmp_path / 'src' / 'main.rs', 'fn main() {}\n')

        result = I007().check(str(tmp_path / 'Cargo.toml'), None, '')

        assert result == []

    def test_no_dependencies_table_stays_silent(self, tmp_path):
        _write(tmp_path / 'Cargo.toml', '[package]\nname = "demo"\nversion = "0.1.0"\n')
        _write(tmp_path / 'src' / 'main.rs', 'fn main() {}\n')

        result = I007().check(str(tmp_path / 'Cargo.toml'), None, '')

        assert result == []


def test_i007_help_and_schema_are_reasonable():
    assert I007.code == 'I007'
    assert set(I007.file_patterns) == {'pyproject.toml', 'requirements.txt', 'Cargo.toml'}


class TestI007UnparsableSource:
    """BACK-1857: a source file that did not parse may be the one using a dependency."""

    @staticmethod
    def _scan(tmp_path, monkeypatch, parse_failed):
        from types import SimpleNamespace
        from reveal.rules.imports import _dep_reconciliation as dr

        (tmp_path / 'broken.py').write_text('import requests\n', encoding='utf-8')

        class Extractor:
            def __init__(self):
                self.parse_failed = parse_failed

            def extract_imports(self, _path):
                return [SimpleNamespace(module_name='requests', is_relative=False, level=0)]

        monkeypatch.setattr(dr, 'get_extractor', lambda _path: Extractor())
        return dr._scan_project_imports_uncached(tmp_path, frozenset({'.py'}), str.lower, '.')

    def test_a_file_that_did_not_parse_is_disclosed_and_its_imports_still_count(self, tmp_path, monkeypatch):
        scan = self._scan(tmp_path, monkeypatch, parse_failed=True)
        assert scan.names == frozenset({'requests'}), 'the imports before the error are real'
        assert [Path(p).name for p in scan.skipped] == ['broken.py']

    def test_a_file_that_parsed_skips_nothing(self, tmp_path, monkeypatch):
        scan = self._scan(tmp_path, monkeypatch, parse_failed=False)
        assert scan.names == frozenset({'requests'}) and scan.skipped == ()
