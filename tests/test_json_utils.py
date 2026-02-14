"""Tests for reveal/utils/json_utils.py - JSON utilities."""

import pytest
import json
from datetime import datetime, date
from reveal.utils.json_utils import DateTimeEncoder, safe_json_dumps


class TestDateTimeEncoder:
    """Test DateTimeEncoder for datetime/date serialization."""

    def test_encode_datetime(self):
        """Encode datetime to ISO format."""
        dt = datetime(2024, 1, 15, 14, 30, 45)
        encoder = DateTimeEncoder()

        result = encoder.default(dt)

        assert result == "2024-01-15T14:30:45"

    def test_encode_date(self):
        """Encode date to ISO format."""
        d = date(2024, 12, 25)
        encoder = DateTimeEncoder()

        result = encoder.default(d)

        assert result == "2024-12-25"

    def test_encode_datetime_with_microseconds(self):
        """Encode datetime with microseconds."""
        dt = datetime(2024, 1, 1, 12, 0, 0, 123456)
        encoder = DateTimeEncoder()

        result = encoder.default(dt)

        assert result == "2024-01-01T12:00:00.123456"

    def test_encode_unsupported_type_raises(self):
        """Raise TypeError for unsupported types."""
        encoder = DateTimeEncoder()

        # Should raise TypeError for unsupported types
        with pytest.raises(TypeError):
            encoder.default(set([1, 2, 3]))

    def test_encode_in_json_dumps(self):
        """Use encoder in json.dumps()."""
        data = {
            'timestamp': datetime(2024, 6, 1, 9, 30, 0),
            'date': date(2024, 6, 1),
            'value': 42
        }

        result = json.dumps(data, cls=DateTimeEncoder)
        decoded = json.loads(result)

        assert decoded['timestamp'] == "2024-06-01T09:30:00"
        assert decoded['date'] == "2024-06-01"
        assert decoded['value'] == 42


class TestSafeJsonDumps:
    """Test safe_json_dumps() convenience function."""

    def test_basic_dict(self):
        """Dump basic dictionary."""
        data = {'key': 'value', 'number': 123}

        result = safe_json_dumps(data)

        # Should be indented (default indent=2)
        assert '"key": "value"' in result
        assert '"number": 123' in result
        assert '\n' in result  # Indented format

    def test_with_datetime(self):
        """Dump dict with datetime."""
        data = {
            'event': 'test',
            'timestamp': datetime(2024, 3, 15, 10, 30, 0)
        }

        result = safe_json_dumps(data)
        decoded = json.loads(result)

        assert decoded['event'] == 'test'
        assert decoded['timestamp'] == "2024-03-15T10:30:00"

    def test_with_date(self):
        """Dump dict with date."""
        data = {
            'event': 'birthday',
            'date': date(1990, 5, 20)
        }

        result = safe_json_dumps(data)
        decoded = json.loads(result)

        assert decoded['date'] == "1990-05-20"

    def test_custom_indent(self):
        """Override default indent."""
        data = {'a': 1, 'b': 2}

        result = safe_json_dumps(data, indent=4)

        # Should use 4-space indent
        assert '    "a": 1' in result or '    "a":1' in result

    def test_no_indent(self):
        """Disable indentation."""
        data = {'x': 10}

        result = safe_json_dumps(data, indent=None)

        # Should be compact (no newlines except maybe at end)
        assert result.strip() == '{"x": 10}' or result.strip() == '{"x":10}'

    def test_custom_encoder_override(self):
        """Allow custom encoder override."""
        class CustomEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, datetime):
                    return "CUSTOM"
                return super().default(obj)

        data = {'time': datetime(2024, 1, 1)}

        result = safe_json_dumps(data, cls=CustomEncoder)

        assert '"CUSTOM"' in result

    def test_kwargs_passthrough(self):
        """Pass through additional json.dumps kwargs."""
        data = {'x': 1, 'a': 2}

        # Test sort_keys parameter
        result = safe_json_dumps(data, sort_keys=True)

        # Keys should be sorted
        lines = [line.strip() for line in result.strip().split('\n')]
        # Find key lines
        key_lines = [l for l in lines if ':' in l and l != '{' and l != '}']
        if key_lines:
            assert '"a"' in key_lines[0]  # 'a' comes before 'x'

    def test_empty_dict(self):
        """Handle empty dictionary."""
        result = safe_json_dumps({})

        decoded = json.loads(result)
        assert decoded == {}

    def test_nested_structures(self):
        """Handle nested structures with dates."""
        data = {
            'records': [
                {'id': 1, 'created': date(2024, 1, 1)},
                {'id': 2, 'created': date(2024, 1, 2)}
            ]
        }

        result = safe_json_dumps(data)
        decoded = json.loads(result)

        assert decoded['records'][0]['created'] == "2024-01-01"
        assert decoded['records'][1]['created'] == "2024-01-02"

    def test_list_with_dates(self):
        """Handle lists containing dates."""
        data = [date(2024, 1, 1), date(2024, 1, 2)]

        result = safe_json_dumps(data)
        decoded = json.loads(result)

        assert decoded == ["2024-01-01", "2024-01-02"]
