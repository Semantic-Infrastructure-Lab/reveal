"""Tests for T006 rule: TypedDict available but function uses bare dict."""
import pytest
from reveal.rules.types.T006 import T006


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
