"""imports' default view spells a folded PHP include's module relative, as ?importers=FILE does (BACK-1096).

`require_once ABSPATH . 'lib.php'` is folded through the project's `define('ABSPATH', __DIR__ . '/')` to a
host path, which the extractor keeps as the statement's module. The ?importers=FILE row relativized it
(`lib.php`); the default view printed the absolute host path, so the two views of one import disagreed
and every such JSON answer carried the analyst's filesystem layout. Found by the oracle-free importer
citation invariant (scripts/graph_invariants.py) on the WordPress corpus: 4 of 4 sampled `constant` rows.
"""
import json

from conftest import _run_reveal_in


def _project(tmp_path):
    proj = tmp_path / 'proj'
    (proj / 'sub').mkdir(parents=True)
    (proj / 'index.php').write_text("<?php\ndefine( 'ABSPATH', __DIR__ . '/' );\nrequire_once ABSPATH . 'lib.php';\n",
                                    encoding='utf-8')
    (proj / 'lib.php').write_text('<?php\nfunction lib() { return 1; }\n', encoding='utf-8')
    (proj / 'sub' / 'page.php').write_text("<?php\nrequire_once ABSPATH . 'lib.php';\n", encoding='utf-8')
    return proj


def _json(tmp_path, uri):
    result = _run_reveal_in(tmp_path, uri, '--format', 'json')
    assert result.returncode == 0, (uri, result.stderr)
    return result.stdout, json.loads(result.stdout)


def test_a_folded_include_module_is_relative_in_the_default_view(tmp_path):
    _project(tmp_path)
    stdout, data = _json(tmp_path, 'imports://proj?root=proj')
    modules = {(f, s['line']): s['module'] for f, stmts in data['files'].items() for s in stmts}
    assert modules == {('index.php', 3): 'lib.php', ('sub/page.php', 2): 'lib.php'}
    assert str(tmp_path) not in stdout and tmp_path.as_posix() not in stdout


def test_the_default_view_and_the_importer_rows_name_the_same_module(tmp_path):
    _project(tmp_path)
    _, default = _json(tmp_path, 'imports://proj?root=proj')
    _, importers = _json(tmp_path, 'imports://proj?importers=lib.php&root=proj')
    rows = {(r['file'], r['line'], r['module']) for r in importers['importers']}
    statements = {(f, s['line'], s['module']) for f, stmts in default['files'].items() for s in stmts}
    assert rows and rows <= statements


def test_an_include_written_absolute_outside_the_tree_keeps_its_spelling(tmp_path):
    """Negative control: only a path under the scan is relativized; an include the author wrote as an
    absolute path outside the project is reported as written."""
    proj = tmp_path / 'cproj'
    proj.mkdir()
    (proj / 'main.c').write_text('#include "/opt/vendor/include/thing.h"\nint main(void) { return 0; }\n',
                                 encoding='utf-8')
    _, data = _json(tmp_path, 'imports://cproj?root=cproj')
    assert [s['module'] for s in data['files']['main.c']] == ['/opt/vendor/include/thing.h']  # noqa: win-path
