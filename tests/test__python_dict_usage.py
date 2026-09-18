"""Direct tests for the untyped-dict usage engine (BACK-1288).

Its behavior is exercised indirectly by T006 and the dict-heatmap tests; these
pin the engine's own contract so a change here fails here first.
"""

import ast

import pytest

from reveal.analyzers import _python_dict_usage as engine

pytestmark = pytest.mark.component


def _func(src):
    return ast.parse(src).body[0]


class TestIsUntypedDict:
    @pytest.mark.parametrize('annotation', ['dict', 'Dict[str, Any]', 'Optional[dict]', '"Dict[str, Any]"'])
    def test_untyped_forms(self, annotation):
        fn = _func(f'def f(d: {annotation}): pass')
        assert engine.is_untyped_dict(fn.args.args[0].annotation)

    @pytest.mark.parametrize('annotation', ['int', 'str', 'list', 'MyRecord'])
    def test_other_types_are_not(self, annotation):
        fn = _func(f'def f(d: {annotation}): pass')
        assert not engine.is_untyped_dict(fn.args.args[0].annotation)


class TestFunctionDictUsages:
    def test_reads_via_subscript_and_get_are_collected(self):
        fn = _func('def f(d: dict):\n    a = d["name"]\n    b = d.get("age")\n')
        (usage,) = engine.function_dict_usages(fn, 'x.py')
        assert usage['param'] == 'd'
        assert usage['keys'] == ['age', 'name']
        assert usage['source'] == 'annotated_param'

    def test_typed_param_is_ignored(self):
        fn = _func('def f(d: int):\n    return d\n')
        assert engine.function_dict_usages(fn, 'x.py') == []
        assert not engine.has_untyped_dict_param(fn)

    def test_only_untyped_params_reported(self):
        fn = _func('def f(d: dict, n: int, e: "Dict[str, Any]"):\n    d["a"]\n    e["b"]\n')
        assert [u['param'] for u in engine.function_dict_usages(fn, 'x.py')] == ['d', 'e']
        assert engine.has_untyped_dict_param(fn)
