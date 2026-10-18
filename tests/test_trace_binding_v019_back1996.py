"""Required declared parameters are authored validation, not init crashes."""
from pathlib import Path
from dataclasses import replace

import pytest

from reveal.adapters.trace import TraceAdapter
from reveal.rules.validation.V019 import V019


def test_declared_missing_selector_is_expected_resource_validation():
    import reveal.adapters.trace as trace
    assert V019()._test_resource_init('trace', TraceAdapter, Path(trace.__file__)) is None


def test_other_value_error_in_required_adapter_remains_a_finding(tmp_path):
    class Broken(TraceAdapter):
        def __init__(self, resource):
            raise ValueError('unexpected internal value')

    source = tmp_path / 'adapter.py'
    source.write_text('class Broken:\n    def __init__(self, resource):\n        pass\n', encoding='utf-8')
    found = V019()._test_resource_init('broken', Broken, source)
    assert found is not None
    assert 'unexpected ValueError' in found.message


def test_undeclared_missing_selector_message_remains_a_finding(tmp_path):
    class Undeclared:
        def __init__(self, resource):
            raise ValueError('from is required')

    source = tmp_path / 'adapter.py'
    source.write_text('class Undeclared:\n    def __init__(self, resource):\n        pass\n', encoding='utf-8')
    assert V019()._test_resource_init('undeclared', Undeclared, source) is not None


@pytest.mark.parametrize('message', [
    'prefix from is required', 'from is required suffix',
    'other is required', 'From is required',
])
def test_declared_required_message_must_match_exactly(tmp_path, message):
    class Broken(TraceAdapter):
        def __init__(self, resource):
            raise ValueError(message)

    source = tmp_path / 'adapter.py'
    source.write_text('class Broken:\n    def __init__(self, resource):\n        pass\n', encoding='utf-8')
    assert V019()._test_resource_init('broken', Broken, source) is not None


def test_optional_parameter_message_remains_a_finding(tmp_path):
    class Broken:
        PARAM_SPECS = (replace(TraceAdapter.PARAM_SPECS[0], required=False),)

        def __init__(self, resource):
            raise ValueError('from is required')

    source = tmp_path / 'adapter.py'
    source.write_text('class Broken:\n    def __init__(self, resource):\n        pass\n', encoding='utf-8')
    assert V019()._test_resource_init('broken', Broken, source) is not None
