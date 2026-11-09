"""BACK-2562: a one-segment ``use`` declaration (``use serde;``, ``pub use reqwest_eventsource;``) is an import.

``_parse_use_declaration`` handled scoped paths, lists, ``as`` clauses and globs but not a bare
identifier, so a crate-to-crate edge like Meilisearch's ``pub use reqwest_eventsource;`` in
async-openai's lib.rs was never extracted and the rust-cargo oracle scored it as missed.
"""

from pathlib import Path

import pytest

from reveal.analyzers.imports.rust import RustExtractor


def _imports(tmp_path, source):
    path = tmp_path / 'lib.rs'
    path.write_text(source, encoding='utf-8')
    return RustExtractor().extract_imports(Path(path))


def _names(statements):
    return [s.module_name for s in statements]


def test_a_bare_use_is_an_import(tmp_path):
    assert _names(_imports(tmp_path, 'use serde;\n')) == ['serde']


def test_a_bare_pub_use_is_an_import_and_a_reexport(tmp_path):
    (statement,) = _imports(tmp_path, 'pub use reqwest_eventsource;\n')
    assert statement.module_name == 'reqwest_eventsource'
    assert statement.skip_unused  # a re-export is for other files to consume, never 'locally unused'


def test_a_bare_use_with_an_alias_keeps_both(tmp_path):
    (statement,) = _imports(tmp_path, 'use tokio as rt;\n')
    assert (statement.module_name, statement.alias) == ('tokio', 'rt')


def test_the_other_forms_are_unchanged(tmp_path):
    source = 'use std::collections::HashMap;\nuse std::{fs, io};\nuse std::io::Result as IoResult;\nuse std::fmt::*;\n'
    statements = _imports(tmp_path, source)
    assert _names(statements) == ['std::collections::HashMap', 'std::fs', 'std::io', 'std::io::Result', 'std::fmt::*']
    assert [s.alias for s in statements][3] == 'IoResult'


@pytest.mark.parametrize('source', ['fn main() {}\n', 'mod inner;\n', '// use serde;\n'])
def test_text_that_is_not_a_use_declaration_adds_nothing(tmp_path, source):
    assert _imports(tmp_path, source) == []
