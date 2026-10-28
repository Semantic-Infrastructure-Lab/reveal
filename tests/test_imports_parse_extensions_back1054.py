"""ImportsAdapter's build for a caller with its own answer shape (BACK-1054 slice S6).

``parse_extensions`` narrows the walk to a caller's extension family (depends:// keeps a file
target's own family, BACK-525 layer 4): only that family is kept, parsed and counted against the
file cap, and the graph cache key names the family. ``analyze()`` returns the build unpresented;
``scan`` and ``scope_hidden`` describe it.
"""
from pathlib import Path

import pytest

from reveal.analyzers.imports import build_cache

from reveal.adapters import imports as imports_mod
from reveal.adapters.imports import ImportsAdapter
from reveal.analyzers.imports.base import get_all_extensions

pytestmark = [pytest.mark.component]

PY = frozenset({'.py', '.pyi'})


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


@pytest.fixture
def tree(tmp_path):
    return _write(tmp_path / 'fx', {
        'pyproject.toml': '[project]\nname = "fx"\n',
        'pkg/__init__.py': '', 'pkg/core.py': 'VALUE = 1\n', 'pkg/a.py': 'from pkg import core\n',
        'web/one.js': "import { x } from './two';\n", 'web/two.js': 'export const x = 1;\n',
        'tools/run.sh': 'echo hi\n',
    })


def test_analyze_returns_the_build_unpresented(tree):
    engine = ImportsAdapter(str(tree))
    analysis = engine.analyze()
    assert analysis is engine.analysis and analysis.graph is not None and analysis.resolution is not None
    assert engine.scan is not None and engine.scan.root == tree.resolve()
    assert engine.scope_hidden is None
    names = {p.name for p in analysis.scanned_files}
    assert {'core.py', 'a.py', 'one.js', 'two.js'} <= names


def test_parse_extensions_keeps_only_that_family(tree):
    analysis = ImportsAdapter(str(tree), parse_extensions=PY).analyze()
    assert {p.suffix for p in analysis.scanned_files} == {'.py'}
    assert analysis.unsupported_extensions == {}  # no recognized-code census outside the family
    assert analysis.graph.reverse_deps[tree.resolve() / 'pkg' / 'core.py'] == {tree.resolve() / 'pkg' / 'a.py'}


def test_without_parse_extensions_recognized_code_counts_against_the_cap(tree):
    """Positive control: the default walk keeps unextractable code (counted for the coverage
    warning) and every family, so a cap of 4 cuts it; the Python family alone fits."""
    capped = ImportsAdapter(str(tree), params={'max_files': 4}).analyze()
    assert capped.resolution.capped is True
    narrowed = ImportsAdapter(str(tree), params={'max_files': 4}, parse_extensions=PY).analyze()
    assert narrowed.resolution.capped is False


def test_the_cache_key_names_the_family(tree, monkeypatch):
    keys = []
    real = build_cache._graph_cache_key

    def recording(*args, **kwargs):
        key = real(*args, **kwargs)
        keys.append(key)
        return key

    monkeypatch.setattr(build_cache, '_graph_cache_key', recording)
    py_only = _write(tree.parent / 'pyonly', {'pyproject.toml': '[project]\nname = "p"\n', 'm.py': 'import os\n'})
    ImportsAdapter(str(py_only)).analyze()
    ImportsAdapter(str(py_only), parse_extensions=frozenset(get_all_extensions())).analyze()
    ImportsAdapter(str(py_only), parse_extensions=PY).analyze()
    # The same walk over every supported extension is the same build; a narrowed family is another.
    assert keys[0] == keys[1] and keys[2] not in (keys[0], None)
