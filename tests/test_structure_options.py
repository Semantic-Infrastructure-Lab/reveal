"""Tests for structure_options module.

Tests the StructureOptions dataclass configuration.
"""

import unittest
from reveal.structure_options import StructureOptions


class TestStructureOptions(unittest.TestCase):
    """Test StructureOptions dataclass."""

    def test_default_initialization(self):
        """Test creating StructureOptions with defaults."""
        opts = StructureOptions()

        # All options should be None or False by default
        assert opts.head is None
        assert opts.tail is None
        assert opts.range is None
        assert opts.extract_links is False
        assert opts.link_type is None
        assert opts.domain is None
        assert opts.broken is False
        assert opts.extract_code is False
        assert opts.language is None
        assert opts.inline_code is False
        assert opts.extract_frontmatter is False
        assert opts.extract_related is False
        assert opts.related_depth == 1
        assert opts.related_limit == 100
        assert opts.semantic is None
        assert opts.metadata is False
        assert opts.scripts is None
        assert opts.styles is None
        assert opts.outline is False
        assert opts.extra == {}

    def test_initialization_with_values(self):
        """Test creating StructureOptions with custom values."""
        opts = StructureOptions(
            head=10,
            extract_links=True,
            link_type='external',
            domain='example.com',
            extract_code=True,
            language='python'
        )

        assert opts.head == 10
        assert opts.extract_links is True
        assert opts.link_type == 'external'
        assert opts.domain == 'example.com'
        assert opts.extract_code is True
        assert opts.language == 'python'

    def test_from_kwargs_with_known_fields(self):
        """Test creating StructureOptions from kwargs with known fields."""
        opts = StructureOptions.from_kwargs(
            head=5,
            extract_links=True,
            outline=True
        )

        assert opts.head == 5
        assert opts.extract_links is True
        assert opts.outline is True
        assert opts.extra == {}

    def test_from_kwargs_with_unknown_fields(self):
        """Test that unknown kwargs go into extra dict."""
        opts = StructureOptions.from_kwargs(
            head=10,
            custom_option='value',
            another_option=42
        )

        assert opts.head == 10
        assert opts.extra == {
            'custom_option': 'value',
            'another_option': 42
        }

    def test_from_kwargs_mixed_known_and_unknown(self):
        """Test from_kwargs with mix of known and unknown fields."""
        opts = StructureOptions.from_kwargs(
            head=20,
            extract_links=True,
            custom_field='custom_value',
            extract_code=True,
            unknown_param=123
        )

        assert opts.head == 20
        assert opts.extract_links is True
        assert opts.extract_code is True
        assert opts.extra == {
            'custom_field': 'custom_value',
            'unknown_param': 123
        }

    def test_to_dict_with_defaults(self):
        """Test to_dict() with default values (should be empty)."""
        opts = StructureOptions()
        result = opts.to_dict()

        # Only non-None and non-False values should be included
        # related_depth=1 and related_limit=100 should be included
        assert result == {
            'related_depth': 1,
            'related_limit': 100
        }

    def test_to_dict_with_values(self):
        """Test to_dict() with custom values."""
        opts = StructureOptions(
            head=10,
            extract_links=True,
            language='python',
            outline=True
        )
        result = opts.to_dict()

        assert result['head'] == 10
        assert result['extract_links'] is True
        assert result['language'] == 'python'
        assert result['outline'] is True
        assert result['related_depth'] == 1
        assert result['related_limit'] == 100

        # False values should not be included (except related_depth/limit defaults)
        assert 'extract_code' not in result
        assert 'broken' not in result

    def test_to_dict_merges_extra_kwargs(self):
        """Test that to_dict() merges extra kwargs into result."""
        opts = StructureOptions(
            head=5,
            extra={'custom_option': 'value', 'another': 42}
        )
        result = opts.to_dict()

        assert result['head'] == 5
        assert result['custom_option'] == 'value'
        assert result['another'] == 42
        assert result['related_depth'] == 1
        assert result['related_limit'] == 100

    def test_to_dict_filters_none_and_false(self):
        """Test that to_dict() filters out None and False values."""
        opts = StructureOptions(
            head=10,
            tail=None,
            extract_links=False,
            language='python',
            domain=None,
            broken=False
        )
        result = opts.to_dict()

        # Only non-None and non-False values
        assert 'head' in result
        assert 'tail' not in result
        assert 'extract_links' not in result
        assert 'language' in result
        assert 'domain' not in result
        assert 'broken' not in result

    def test_roundtrip_from_kwargs_to_dict(self):
        """Test creating from kwargs and converting back to dict."""
        original_kwargs = {
            'head': 15,
            'extract_links': True,
            'language': 'javascript',
            'custom_field': 'custom_value'
        }

        opts = StructureOptions.from_kwargs(**original_kwargs)
        result = opts.to_dict()

        # All original kwargs should be in result
        assert result['head'] == 15
        assert result['extract_links'] is True
        assert result['language'] == 'javascript'
        assert result['custom_field'] == 'custom_value'


if __name__ == '__main__':
    unittest.main()
