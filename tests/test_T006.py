"""Tests for T006 rule: TypedDict available but function uses bare dict."""
import os
import textwrap
from unittest import mock

import pytest
from reveal.rules.types.T006 import T006, _build_index, _clear_index, get_scan_disclosures

# BACK-1149: component-layer test -- single rule/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


class TestT006Attributes:
    def test_rule_attributes(self):
        rule = T006()
        assert rule.code == "T006"
        assert rule.severity.name == "LOW"
        assert '.py' in rule.file_patterns

    def test_invalid_python_returns_empty(self):
        rule = T006()
        detections = rule.check("file.py", None, "def (: this is not python")
        assert len(detections) == 0


class TestT006NoFireConditions:
    """Rule must NOT fire when the trigger conditions aren't met."""

    def test_no_typeddict_defined(self):
        content = "def f(trade: dict): x = trade['a']; y = trade['b']; z = trade['c']"
        assert len(T006().check("f.py", None, content)) == 0

    def test_fewer_than_3_keys_accessed(self):
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str
def f(trade: dict):
    x = trade['a']
    y = trade['b']
"""
        assert len(T006().check("f.py", None, content)) == 0

    def test_unannotated_param_not_flagged(self):
        # T005 handles unannotated params — T006 should skip them
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str
def f(trade):  # no annotation
    x = trade['a']
    y = trade['b']
    z = trade['c']
"""
        assert len(T006().check("f.py", None, content)) == 0

    def test_no_key_accesses(self):
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str
def f(trade: dict) -> bool:
    return bool(trade)
"""
        assert len(T006().check("f.py", None, content)) == 0

    def test_no_overlapping_keys(self):
        content = """\
from typing import TypedDict
class TS(TypedDict):
    x: str
    y: str
    z: str
def f(trade: dict):
    a = trade['a']
    b = trade['b']
    c = trade['c']
"""
        assert len(T006().check("f.py", None, content)) == 0


class TestT006ClassBasedTypedDict:
    """Detection using class-based TypedDict definition."""

    def test_basic_detection(self):
        content = """\
from typing import TypedDict
class TradeState(TypedDict):
    symbol: str
    pnl: float
    outcome: str

def process(trade: dict) -> bool:
    x = trade['symbol']
    y = trade['pnl']
    z = trade['outcome']
    return True
"""
        detections = T006().check("f.py", None, content)
        assert len(detections) == 1

    def test_message_contains_typeddict_name(self):
        content = """\
from typing import TypedDict
class TradeState(TypedDict):
    symbol: str
    pnl: float
    outcome: str

def process(trade: dict):
    a = trade['symbol']
    b = trade['pnl']
    c = trade['outcome']
"""
        d = T006().check("f.py", None, content)[0]
        assert "TradeState" in d.message
        assert "trade" in d.message

    def test_suggestion_contains_typeddict_name(self):
        content = """\
from typing import TypedDict
class TradeState(TypedDict):
    symbol: str
    pnl: float
    outcome: str

def process(trade: dict):
    a = trade['symbol']
    b = trade['pnl']
    c = trade['outcome']
"""
        d = T006().check("f.py", None, content)[0]
        assert "TradeState" in d.suggestion

    def test_context_shows_accessed_keys(self):
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str

def f(x: dict):
    r = x['a'] + x['b'] + x['c']
"""
        d = T006().check("f.py", None, content)[0]
        assert "a" in d.context
        assert "b" in d.context
        assert "c" in d.context

    def test_correct_line_number(self):
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str

def f(x: dict):
    r = x['a'] + x['b'] + x['c']
"""
        d = T006().check("f.py", None, content)[0]
        assert d.line == 7

    def test_async_function_detected(self):
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str

async def f(x: dict):
    r = x['a'] + x['b'] + x['c']
"""
        assert len(T006().check("f.py", None, content)) == 1


class TestT006FunctionalTypedDict:
    """Detection using functional TypedDict definition."""

    def test_keyword_form(self):
        content = """\
from typing import TypedDict
TS = TypedDict('TS', a=str, b=str, c=str)

def f(x: dict):
    return x['a'] + x['b'] + x['c']
"""
        assert len(T006().check("f.py", None, content)) == 1

    def test_dict_literal_form(self):
        content = """\
from typing import TypedDict
TS = TypedDict('TS', {'a': str, 'b': str, 'c': str})

def f(x: dict):
    return x['a'] + x['b'] + x['c']
"""
        assert len(T006().check("f.py", None, content)) == 1


class TestT006BestMatch:
    """When multiple TypedDicts exist, rule picks the best match."""

    def test_picks_highest_overlap(self):
        content = """\
from typing import TypedDict
class Short(TypedDict):
    a: str
    b: str
    c: str

class Long(TypedDict):
    a: str
    b: str
    c: str
    d: str

def f(x: dict):
    return x['a'] + x['b'] + x['c'] + x['d']
"""
        d = T006().check("f.py", None, content)[0]
        # Long has 4 matching keys vs Short's 3 — Long should win
        assert "Long" in d.message

    def test_multiple_params_each_flagged(self):
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str

def f(x: dict, y: dict):
    x['a']; x['b']; x['c']
    y['a']; y['b']; y['c']
"""
        detections = T006().check("f.py", None, content)
        assert len(detections) == 2
        # message contains "'x: dict'" and "'y: dict'"
        assert any("'x:" in d.message for d in detections)
        assert any("'y:" in d.message for d in detections)


class TestT006DictAnnotationVariants:
    """Both bare dict and Dict[K, V] should be treated as bare dict."""

    def test_bare_dict(self):
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str
def f(x: dict): x['a']; x['b']; x['c']
"""
        assert len(T006().check("f.py", None, content)) == 1

    def test_typed_dict_annotation_name(self):
        # If already annotated with a TypedDict, shouldn't fire
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str
def f(x: TS): x['a']; x['b']; x['c']
"""
        assert len(T006().check("f.py", None, content)) == 0


class TestT006KeyReadsAndAnnotations:
    """The shared engine's key-read and annotation coverage, applied to T006."""

    TD = """\
from typing import TypedDict, Optional, Dict, Any, Mapping
class TS(TypedDict):
    a: str
    b: str
    c: str
"""

    def _fires(self, body: str) -> bool:
        return len(T006().check("f.py", None, self.TD + textwrap.dedent(body))) == 1

    def test_get_and_membership_reads_count(self):
        assert self._fires("def f(x: dict):\n    x.get('a'); x.pop('b', None)\n    if 'c' in x: pass\n")

    def test_optional_mapping_and_any_annotations(self):
        assert self._fires("def f(x: Optional[Dict[str, Any]]): x['a']; x['b']; x['c']\n")
        assert self._fires("def f(x: Mapping[str, Any]): x['a']; x['b']; x['c']\n")
        assert self._fires("def f(x: Any): x['a']; x['b']; x['c']\n")

    def test_same_module_dict_alias(self):
        assert self._fires("Cfg = Dict[str, Any]\ndef f(x: Cfg): x['a']; x['b']; x['c']\n")

    def test_message_shows_real_annotation(self):
        d = T006().check("f.py", None, self.TD + "def f(x: Mapping[str, Any]): x['a']; x['b']; x['c']\n")[0]
        assert "'x: Mapping[str, Any]'" in d.message
        assert "Replace 'Mapping[str, Any]' with 'TS'" in d.suggestion

    def test_mostly_unrelated_keys_do_not_fire(self):
        # 3 of 6 keys match -- the TypedDict doesn't explain what the function reads
        assert not self._fires("def f(x: dict): x['a']; x['b']; x['c']; x['p']; x['q']; x['r']\n")

    def test_undeclared_keys_named_in_context(self):
        d = T006().check("f.py", None, self.TD + "def f(x: dict): x['a']; x['b']; x['c']; x['z']\n")[0]
        assert "not declared on TS: z" in d.context

    def test_loop_vars_and_locals_do_not_fire(self):
        assert not self._fires(
            "def f(rows):\n"
            "    for r in rows:\n"
            "        r['a']; r['b']; r['c']\n"
            "    cfg = load()\n"
            "    cfg['a']; cfg['b']; cfg['c']\n"
        )

    def test_subclass_of_typeddict_inherits_fields(self):
        content = """\
from typing import TypedDict
class Base(TypedDict):
    a: str
    b: str
class Child(Base, total=False):
    c: str
def f(x: dict): x['a']; x['b']; x['c']
"""
        d = T006().check("f.py", None, content)[0]
        assert "Child" in d.message


class TestT006CrossModule:
    """The TypedDict lives in another module of the same project."""

    @pytest.fixture(autouse=True)
    def _project(self, tmp_path):
        _clear_index()
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "t"\n')
        (tmp_path / "pkg").mkdir()
        self.root = tmp_path
        yield
        _clear_index()

    def _write(self, rel: str, content: str) -> str:
        path = self.root / rel
        path.write_text(textwrap.dedent(content))
        return str(path)

    def _check(self, rel: str, content: str):
        return T006().check(self._write(rel, content), None, textwrap.dedent(content))

    def test_typeddict_in_other_module_fires_with_location(self):
        self._write("pkg/types_.py", """\
            from typing import TypedDict
            class Element(TypedDict, total=False):
                name: str
                line: int
                calls: list
                complexity: int
        """)
        detections = self._check("pkg/render.py", """\
            def render(elem: dict):
                return elem['name'], elem.get('line'), elem['calls'], elem['complexity']
        """)
        assert len(detections) == 1
        assert "Element" in detections[0].message
        assert "types_.py:2" in detections[0].suggestion

    def test_three_generic_keys_from_other_module_do_not_fire(self):
        """A reader of some other {file, line, name} record must not be told to
        adopt an unrelated TypedDict that happens to declare those keys."""
        self._write("pkg/types_.py", """\
            from typing import TypedDict
            class Element(TypedDict, total=False):
                file: str
                line: int
                name: str
                calls: list
        """)
        assert self._check("pkg/surface.py", """\
            def add_once(entry: dict):
                return entry['file'], entry['line'], entry['name']
        """) == []

    def test_dict_alias_from_other_module(self):
        self._write("pkg/typing_.py", """\
            from typing import Any, Dict, TypedDict
            ConfigType = Dict[str, Any]
            class Config(TypedDict):
                host: str
                port: int
                name: str
                timeout: int
        """)
        detections = self._check("pkg/app.py", """\
            def setup(config: ConfigType):
                return config['host'], config['port'], config['name'], config['timeout']
        """)
        assert len(detections) == 1
        assert "'config: ConfigType'" in detections[0].message

    def test_local_subclass_of_project_typeddict(self):
        self._write("pkg/base.py", """\
            from typing import TypedDict
            class Base(TypedDict):
                a: str
                b: str
        """)
        detections = self._check("pkg/use.py", """\
            from pkg.base import Base
            class Child(Base):
                c: str
            def f(x: dict): x['a']; x['b']; x['c']
        """)
        assert len(detections) == 1
        assert "Child" in detections[0].message

    def test_local_definition_wins_same_name(self):
        self._write("pkg/other.py", """\
            from typing import TypedDict
            class TS(TypedDict):
                a: str
                b: str
                c: str
        """)
        detections = self._check("pkg/mine.py", """\
            from typing import TypedDict
            class TS(TypedDict):
                a: str
                b: str
                c: str
            def f(x: dict): x['a']; x['b']; x['c']
        """)
        assert len(detections) == 1
        assert "defined at" not in detections[0].suggestion

    def test_phantom_path_ignores_project(self):
        self._write("pkg/types_.py", """\
            from typing import TypedDict
            class Element(TypedDict):
                name: str
                line: int
                calls: list
        """)
        content = "def render(elem: dict): elem['name']; elem['line']; elem['calls']\n"
        assert T006().check(str(self.root / "pkg" / "not_on_disk.py"), None, content) == []

    def test_ceiling_disables_cross_module_and_discloses(self):
        self._write("pkg/types_.py", """\
            from typing import TypedDict
            class Element(TypedDict):
                name: str
                line: int
                calls: list
        """)
        with mock.patch.dict(os.environ, {"REVEAL_T006_MAX_FILES": "1"}):
            detections = self._check("pkg/render.py", """\
                def render(elem: dict): elem['name']; elem['line']; elem['calls']
            """)
        assert detections == []
        assert any("REVEAL_T006_MAX_FILES" in d for d in get_scan_disclosures())

    def test_index_skips_files_without_type_facts(self):
        self._write("pkg/plain.py", "def g():\n    return 1\n")
        self._write("pkg/types_.py", """\
            from typing import TypedDict
            class Element(TypedDict):
                name: str
        """)
        index = _build_index(self.root)
        assert [td['name'] for td in index['typeddicts']] == ['Element']


class TestT006EmptyFile:
    def test_empty_returns_empty(self):
        assert T006().check("f.py", None, "") == []

    def test_no_functions_returns_empty(self):
        content = """\
from typing import TypedDict
class TS(TypedDict):
    a: str
    b: str
    c: str
"""
        assert len(T006().check("f.py", None, content)) == 0
