"""ast:// name/type queries pick their files from the outline (BACK-1867).

The answer must be exactly the full scan's: same elements, same order, same file count and
warnings. The cases are the ones an outline gets wrong if it is applied carelessly: a file with
only imports (empty outline, still counted), an import whose text is the queried name (the
outline has no imports), and every query shape that needs metrics, which must stay on the
full path. A counter shows the metrics walk runs only for the files the query touches.
"""

import json
import os
from pathlib import Path

import pytest

from reveal import treesitter as ts_mod
from reveal.adapters.ast import adapter as ast_adapter
from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast.filtering import outline_plan
from reveal.adapters.ast.queries import parse_query

pytestmark = [pytest.mark.component, pytest.mark.disk_cache]


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    ts_mod._get_parse_cache().clear()
    yield
    ts_mod._get_parse_cache().clear()


def _plan(query_string, sort=None):
    return outline_plan(parse_query(query_string), sort)


@pytest.mark.parametrize("query,sort,expected", [
    ("name=parse", None, (True, "parse")),            # exact, untyped: imports checked by text
    ("name=pars*", None, (True, None)),               # untyped glob drops imports itself
    ("type=function&name=parse", None, (True, None)),
    ("type=function,class&name=*Foo", None, (True, None)),
    ("type=function&name=parse", "line", (True, None)),
    ("type=function&name=parse", "name", (True, None)),
    ("type=import&name=os", None, (False, None)),     # the outline has no imports
    ("type=function,import&name=os", None, (False, None)),
    ("name=parse", "complexity", (False, None)),      # sort needs a metric
    ("name=parse&lines>5", None, (False, None)),      # filter on another key
    ("name=parse&complexity>3", None, (False, None)),
    ("type=function", None, (False, None)),           # no name: every file matches, no gain
    ("name~=par.*", None, (False, None)),             # untyped regex could hit an import
    ("name!=x", None, (False, None)),
    ("type=function&name~=par.*", None, (True, None)),  # typed regex is decided on names alone
])
def test_which_queries_may_use_the_outline(query, sort, expected):
    assert _plan(query, sort) == expected


GO_A = """package a

import "parse"
import "fmt"

func Parse() int { if true { return 1 }; return 2 }
func helper() int { return 3 }
"""
GO_B = """package b

func Parse() int { for i := 0; i < 3; i++ { if i > 1 { return i } }; return 0 }
"""
GO_IMPORTS_ONLY = """package c

import "fmt"
"""
GO_UNRELATED = """package d

func other() int { return 9 }
func another() int { return 8 }
"""


@pytest.fixture
def tree(tmp_path):
    for name, src in {"a.go": GO_A, "b.go": GO_B, "c.go": GO_IMPORTS_ONLY, "d.go": GO_UNRELATED}.items():
        (tmp_path / name).write_text(src, encoding="utf-8")
    return tmp_path


_runs = iter(range(10**6))


def _run(path, query, full=False, monkeypatch=None):
    ts_mod._get_parse_cache().clear()
    os.environ["REVEAL_CACHE_DIR"] = str(Path(os.environ["REVEAL_CACHE_DIR"]).parent / f"run{next(_runs)}")
    if full:
        monkeypatch.setattr(ast_adapter, "outline_plan", lambda *a, **k: (False, None))
    adapter = AstAdapter(str(path), query)
    result = adapter.get_structure()
    return json.loads(json.dumps(result, default=str))


IMPORT_QUERY = 'name=import "parse"'   # an import element is named by its whole statement
QUERIES = ["name=Parse", "name=Par*", "type=function&name=Parse", "name=parse", IMPORT_QUERY, "name=fmt",
           "type=function,class&name=*e", "name=Parse&sort=-line&limit=1", "name=nothing"]


@pytest.mark.parametrize("query", QUERIES)
def test_the_outline_scan_returns_what_the_full_scan_returns(tree, query, monkeypatch):
    with monkeypatch.context() as m:
        expected = _run(tree, query, full=True, monkeypatch=m)
    got = _run(tree, query)
    for key in ("total_files", "total_results", "displayed_results", "results", "query"):
        assert got[key] == expected[key], key
    assert got["meta"]["warnings"] == expected["meta"]["warnings"]
    assert got["meta"]["confidence"] == expected["meta"]["confidence"]


def test_the_cases_are_not_vacuous(tree):
    """Controls: the import named by the query is a result, and the import-only file is counted."""
    assert _run(tree, IMPORT_QUERY)["total_results"] == 1       # the import in a.go, found by text
    assert _run(tree, "name=Parse")["total_results"] == 2        # a.go and b.go
    assert _run(tree, "name=Parse")["total_files"] == 4          # c.go (imports only) too


def test_metrics_are_computed_only_for_the_files_a_query_touches(tree, monkeypatch):
    walks = []
    original = ts_mod.TreeSitterAnalyzer._complexity_depth_and_calls

    def counting(self, *a, **k):
        walks.append(self.path)
        return original(self, *a, **k)

    monkeypatch.setattr(ts_mod.TreeSitterAnalyzer, "_complexity_depth_and_calls", counting)
    _run(tree, "type=function&name=Parse")
    touched = {Path(p).name for p in walks}
    assert touched == {"a.go", "b.go"}, touched          # d.go's functions were never measured
    walks.clear()
    _run(tree, "type=function&name=Parse&complexity>0")   # needs metrics: the full scan (control)
    assert {Path(p).name for p in walks} == {"a.go", "b.go", "d.go"}
