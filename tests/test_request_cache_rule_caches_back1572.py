"""I007's project import scan and L001's anchor cache follow edits across MCP requests (BACK-1572).

Both were reproduced stale (Sprint 4 review F-STALE-1): they outlived a request, so a
second ``reveal_check`` in the same process answered from the tree as it was first seen.
A request here is reset -> evaluate -> seal, the order mcp_server.request() uses.
"""
from pathlib import Path

from reveal.analyzers.imports.generic import _ruby_gem_inventory
from reveal.analyzers.imports.javascript import (
    _find_tsconfig, _find_workspace_packages, _get_tsconfig_aliases)
from reveal.analyzers.imports.rust import _rust_crate_inventory
from reveal.rules.imports import _dep_reconciliation as dep
from reveal.rules.imports.I003 import I003
from reveal.rules.links.L001 import L001
from reveal.rules.urls.U502 import U502
from reveal.utils.request_cache import (
    request_started_ns, reset_request_caches, seal_request_caches)

PY = frozenset({'.py'})


def _request(evaluate):
    """One serialized host request around *evaluate*."""
    started = request_started_ns()
    reset_request_caches()
    try:
        return evaluate()
    finally:
        seal_request_caches(started)


def _imported(root: Path) -> frozenset:
    return _request(lambda: dep._scan_project_imports(
        root, PY, dep._fold_hyphen_underscore, '.')).names


def test_i007_scan_sees_an_import_added_between_requests(tmp_path):
    src = tmp_path / 'app.py'
    src.write_text('import requests\n', encoding='utf-8')
    assert _imported(tmp_path) == {'requests'}
    src.write_text('import requests\nimport yaml_extra_dep\n', encoding='utf-8')
    assert _imported(tmp_path) == {'requests', 'yaml_extra_dep'}


def test_i007_scan_sees_an_import_removed_between_requests(tmp_path):
    src = tmp_path / 'app.py'
    src.write_text('import requests\nimport flask\n', encoding='utf-8')
    assert _imported(tmp_path) == {'requests', 'flask'}
    src.write_text('import requests\n', encoding='utf-8')
    assert _imported(tmp_path) == {'requests'}


def test_i007_scan_is_reused_while_the_tree_is_unchanged(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text('import requests\n', encoding='utf-8')
    assert _imported(tmp_path) == {'requests'}
    calls = []
    real = dep._walk_code_files
    monkeypatch.setattr(dep, '_walk_code_files', lambda *a, **k: calls.append(1) or real(*a, **k))
    assert _imported(tmp_path) == {'requests'}
    assert calls == [], "an unchanged tree must not be rescanned"


def _anchors(target: Path):
    return _request(lambda: L001()._extract_anchors_from_markdown(target))


def test_l001_anchors_follow_a_heading_edit_between_requests(tmp_path):
    doc = tmp_path / 'target.md'
    doc.write_text('# Alpha\n', encoding='utf-8')
    assert _anchors(doc) == ['alpha']
    doc.write_text('# Beta\n', encoding='utf-8')
    assert _anchors(doc) == ['beta']


# ---- the inventories and per-directory config caches the review named "by inspection" ----


def test_rust_crate_inventory_follows_a_cargo_edit(tmp_path):
    manifest = tmp_path / 'Cargo.toml'
    manifest.write_text('[package]\nname = "mylib"\n[dependencies]\nserde = "1"\n', encoding='utf-8')
    assert 'serde' in _request(lambda: _rust_crate_inventory(tmp_path))[1]
    manifest.write_text('[package]\nname = "mylib"\n[dependencies]\ntokio_rt = "1"\n', encoding='utf-8')
    external = _request(lambda: _rust_crate_inventory(tmp_path))[1]
    assert 'tokio_rt' in external and 'serde' not in external


def test_ruby_gem_inventory_follows_a_gemfile_lock_edit(tmp_path):
    lock = tmp_path / 'Gemfile.lock'
    lock.write_text('GEM\n  specs:\n    rack (3.0.0)\n', encoding='utf-8')
    assert 'rack' in _request(lambda: _ruby_gem_inventory(tmp_path))[1]
    lock.write_text('GEM\n  specs:\n    sinatra (4.0.0)\n', encoding='utf-8')
    external = _request(lambda: _ruby_gem_inventory(tmp_path))[1]
    assert 'sinatra' in external and 'rack' not in external


def test_i003_layer_config_follows_a_reveal_yaml_edit(tmp_path):
    cfg = tmp_path / '.reveal.yaml'
    cfg.write_text('layers:\n  - name: core\n    paths: ["core/**"]\n    allow_imports: []\n', encoding='utf-8')
    first = _request(lambda: I003()._load_config_and_find_root(tmp_path))
    assert first[0] is not None
    cfg.unlink()
    assert _request(lambda: I003()._load_config_and_find_root(tmp_path)) == (None, None, None)


def test_u502_canonical_urls_follow_a_pyproject_edit(tmp_path):
    pp = tmp_path / 'pyproject.toml'
    pp.write_text('[project]\nname="x"\n[project.urls]\nHome = "https://github.com/a/one"\n', encoding='utf-8')
    assert _request(lambda: U502()._get_canonical_urls(pp)) == {'https://github.com/a/one'}
    pp.write_text('[project]\nname="x"\n[project.urls]\nHome = "https://github.com/a/two"\n', encoding='utf-8')
    assert _request(lambda: U502()._get_canonical_urls(pp)) == {'https://github.com/a/two'}


def test_u502_pyproject_lookup_follows_a_new_pyproject(tmp_path):
    sub = tmp_path / 'pkg'
    sub.mkdir()
    assert _request(lambda: U502()._find_pyproject(sub)) is None
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="x"\n', encoding='utf-8')
    assert _request(lambda: U502()._find_pyproject(sub)) == tmp_path / 'pyproject.toml'


def test_tsconfig_lookup_follows_a_new_tsconfig(tmp_path):
    sub = tmp_path / 'src'
    sub.mkdir()
    assert _request(lambda: _find_tsconfig(sub, tmp_path)) is None
    (tmp_path / 'tsconfig.json').write_text('{}', encoding='utf-8')
    assert _request(lambda: _find_tsconfig(sub, tmp_path)) == (tmp_path / 'tsconfig.json').resolve()


def test_tsconfig_aliases_follow_a_paths_edit(tmp_path):
    cfg = tmp_path / 'tsconfig.json'
    cfg.write_text('{"compilerOptions": {"paths": {"@a/*": ["src/a/*"]}}}', encoding='utf-8')
    assert set(_request(lambda: _get_tsconfig_aliases(cfg))[1]) == {'@a/*'}
    cfg.write_text('{"compilerOptions": {"paths": {"@b/*": ["src/b/*"]}}}', encoding='utf-8')
    assert set(_request(lambda: _get_tsconfig_aliases(cfg))[1]) == {'@b/*'}


def test_workspace_packages_follow_a_new_member(tmp_path):
    (tmp_path / 'package.json').write_text('{"workspaces": ["packages/*"]}', encoding='utf-8')
    one = tmp_path / 'packages' / 'one'
    one.mkdir(parents=True)
    (one / 'package.json').write_text('{"name": "@org/one"}', encoding='utf-8')
    assert set(_request(lambda: _find_workspace_packages(tmp_path))) == {'@org/one'}
    two = tmp_path / 'packages' / 'two'
    two.mkdir()
    (two / 'package.json').write_text('{"name": "@org/two"}', encoding='utf-8')
    assert set(_request(lambda: _find_workspace_packages(tmp_path))) == {'@org/one', '@org/two'}
