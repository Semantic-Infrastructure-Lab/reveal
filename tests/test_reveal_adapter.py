"""Tests for reveal/adapters/reveal.py - reveal:// self-inspection adapter.

Tests the meta-adapter that allows reveal to inspect its own codebase,
discover analyzers, rules, and adapters.
"""

import json
import pytest
from pathlib import Path
from reveal.adapters.reveal import RevealAdapter


class TestRevealAdapterHelp:
    """Test get_help() static method."""

    def test_help_has_required_fields(self):
        """Help contains all required documentation fields."""
        help_doc = RevealAdapter.get_help()

        assert 'name' in help_doc
        assert help_doc['name'] == 'reveal'
        assert 'description' in help_doc
        assert 'syntax' in help_doc
        assert 'examples' in help_doc

    def test_help_has_examples(self):
        """Help includes practical examples."""
        help_doc = RevealAdapter.get_help()

        assert len(help_doc['examples']) > 0
        for example in help_doc['examples']:
            assert 'uri' in example
            assert 'description' in example

    def test_help_has_validation_rules(self):
        """Help documents validation rules."""
        help_doc = RevealAdapter.get_help()

        assert 'validation_rules' in help_doc
        rules = help_doc['validation_rules']
        assert 'V001' in rules
        assert 'V002' in rules

    def test_help_has_workflows(self):
        """Help includes workflow examples."""
        help_doc = RevealAdapter.get_help()

        assert 'workflows' in help_doc
        assert len(help_doc['workflows']) > 0

    def test_help_has_try_now(self):
        """Help has quick-start commands."""
        help_doc = RevealAdapter.get_help()

        assert 'try_now' in help_doc
        assert 'reveal reveal://' in help_doc['try_now']


class TestRevealAdapterInit:
    """Test adapter initialization."""

    def test_init_no_component(self):
        """Initialize without component."""
        adapter = RevealAdapter()
        assert adapter.component is None
        assert adapter.reveal_root is not None

    def test_init_with_component(self):
        """Initialize with specific component."""
        adapter = RevealAdapter(component='analyzers')
        assert adapter.component == 'analyzers'

    def test_finds_reveal_root(self):
        """Adapter finds reveal's root directory."""
        adapter = RevealAdapter()

        # Should find a directory with analyzers and rules
        assert adapter.reveal_root.exists()
        assert (adapter.reveal_root / 'analyzers').exists() or \
               adapter.reveal_root.name == 'reveal'


class TestRevealAdapterGetAnalyzers:
    """Test analyzer discovery."""

    def test_get_analyzers_returns_list(self):
        """_get_analyzers returns a list."""
        adapter = RevealAdapter()
        analyzers = adapter._get_analyzers()

        assert isinstance(analyzers, list)

    def test_get_analyzers_has_expected_types(self):
        """_get_analyzers finds common analyzers."""
        adapter = RevealAdapter()
        analyzers = adapter._get_analyzers()
        names = {a['name'] for a in analyzers}

        # Should find at least some core analyzers
        expected = {'python', 'markdown', 'rust', 'go'}
        found = expected.intersection(names)
        assert len(found) > 0, f"Expected to find some of {expected}, got {names}"

    def test_analyzer_entry_format(self):
        """Analyzer entries have expected fields."""
        adapter = RevealAdapter()
        analyzers = adapter._get_analyzers()

        if analyzers:
            analyzer = analyzers[0]
            assert 'name' in analyzer
            assert 'path' in analyzer
            assert 'module' in analyzer

    def test_skips_private_files(self):
        """Analyzers starting with _ are skipped."""
        adapter = RevealAdapter()
        analyzers = adapter._get_analyzers()
        names = {a['name'] for a in analyzers}

        # __init__ should be skipped
        assert '__init__' not in names
        assert not any(n.startswith('_') for n in names)


class TestRevealAdapterGetAdapters:
    """Test adapter discovery."""

    def test_get_adapters_returns_list(self):
        """_get_adapters returns a list."""
        adapter = RevealAdapter()
        adapters = adapter._get_adapters()

        assert isinstance(adapters, list)

    def test_get_adapters_finds_itself(self):
        """_get_adapters includes reveal:// adapter."""
        adapter = RevealAdapter()
        adapters = adapter._get_adapters()
        schemes = {a['scheme'] for a in adapters}

        assert 'reveal' in schemes

    def test_get_adapters_finds_common(self):
        """_get_adapters finds common adapters."""
        adapter = RevealAdapter()
        adapters = adapter._get_adapters()
        schemes = {a['scheme'] for a in adapters}

        # Should find core adapters
        expected = {'reveal', 'help', 'env', 'ast'}
        found = expected.intersection(schemes)
        assert len(found) >= 2, f"Expected to find some of {expected}, got {schemes}"

    def test_adapter_entry_format(self):
        """Adapter entries have expected fields."""
        adapter = RevealAdapter()
        adapters = adapter._get_adapters()

        if adapters:
            entry = adapters[0]
            assert 'scheme' in entry
            assert 'class' in entry
            assert 'module' in entry
            assert 'has_help' in entry


class TestRevealAdapterGetRules:
    """Test rule discovery."""

    def test_get_rules_returns_list(self):
        """_get_rules returns a list."""
        adapter = RevealAdapter()
        rules = adapter._get_rules()

        assert isinstance(rules, list)

    def test_get_rules_finds_some(self):
        """_get_rules finds at least some rules."""
        adapter = RevealAdapter()
        rules = adapter._get_rules()

        # Should find at least a few rules
        assert len(rules) > 0

    def test_rule_entry_format(self):
        """Rule entries have expected fields."""
        adapter = RevealAdapter()
        rules = adapter._get_rules()

        if rules:
            rule = rules[0]
            assert 'code' in rule
            assert 'category' in rule
            assert 'path' in rule
            assert 'module' in rule

    def test_rules_sorted_by_code(self):
        """Rules are sorted by code."""
        adapter = RevealAdapter()
        rules = adapter._get_rules()

        if len(rules) > 1:
            codes = [r['code'] for r in rules]
            assert codes == sorted(codes)


class TestRevealAdapterGetStructure:
    """Test full structure retrieval."""

    def test_get_structure_returns_dict(self):
        """get_structure returns a dict."""
        adapter = RevealAdapter()
        structure = adapter.get_structure()

        assert isinstance(structure, dict)

    def test_get_structure_has_sections(self):
        """get_structure has all expected sections."""
        adapter = RevealAdapter()
        structure = adapter.get_structure()

        assert 'analyzers' in structure
        assert 'adapters' in structure
        assert 'rules' in structure
        assert 'metadata' in structure

    def test_get_structure_metadata(self):
        """get_structure metadata has counts."""
        adapter = RevealAdapter()
        structure = adapter.get_structure()
        meta = structure['metadata']

        assert 'root' in meta
        assert 'analyzers_count' in meta
        assert 'adapters_count' in meta
        assert 'rules_count' in meta


class TestRevealAdapterFormatOutput:
    """Test output formatting."""

    def test_format_text(self):
        """format_output produces text output."""
        adapter = RevealAdapter()
        structure = adapter.get_structure()
        output = adapter.format_output(structure, 'text')

        assert isinstance(output, str)
        assert '# Reveal Internal Structure' in output
        assert '## Analyzers' in output or 'Analyzers' in output

    def test_format_json(self):
        """format_output produces valid JSON."""
        adapter = RevealAdapter()
        structure = adapter.get_structure()
        output = adapter.format_output(structure, 'json')

        # Should be valid JSON
        parsed = json.loads(output)
        assert 'analyzers' in parsed
        assert 'metadata' in parsed

    def test_format_text_shows_adapters(self):
        """Text output includes adapter section."""
        adapter = RevealAdapter()
        structure = adapter.get_structure()
        output = adapter.format_output(structure, 'text')

        assert '## Adapters' in output or 'Adapters' in output

    def test_format_text_shows_rules(self):
        """Text output includes rules section."""
        adapter = RevealAdapter()
        structure = adapter.get_structure()
        output = adapter.format_output(structure, 'text')

        # Should have rules or at least metadata about them
        assert 'Rules' in output or 'rules_count' in output


class TestRevealAdapterElementExtraction:
    """Test element extraction from reveal source files."""

    def test_get_element_python_function(self, capsys):
        """Extract a Python function from reveal source."""
        from argparse import Namespace
        adapter = RevealAdapter()
        args = Namespace(format='text')

        # Extract a function from L001 rule
        result = adapter.get_element('rules/links/L001.py', '_extract_anchors_from_markdown', args)

        assert result is True
        captured = capsys.readouterr()
        assert '_extract_anchors_from_markdown' in captured.out
        assert 'def _extract_anchors_from_markdown' in captured.out

    def test_get_element_python_class(self, capsys):
        """Extract a Python class from reveal source."""
        from argparse import Namespace
        adapter = RevealAdapter()
        args = Namespace(format='text')

        # Extract MarkdownAnalyzer class
        result = adapter.get_element('analyzers/markdown.py', 'MarkdownAnalyzer', args)

        assert result is True
        captured = capsys.readouterr()
        assert 'MarkdownAnalyzer' in captured.out
        assert 'class MarkdownAnalyzer' in captured.out

    def test_get_element_nonexistent_file(self):
        """get_element returns None for nonexistent file."""
        from argparse import Namespace
        adapter = RevealAdapter()
        args = Namespace(format='text')

        result = adapter.get_element('nonexistent/file.py', 'SomeElement', args)

        assert result is None

    def test_get_element_self_referential(self, capsys):
        """Extract element from RevealAdapter itself."""
        from argparse import Namespace
        adapter = RevealAdapter()
        args = Namespace(format='text')

        # Extract get_element method from RevealAdapter
        result = adapter.get_element('adapters/reveal.py', 'get_element', args)

        assert result is True
        captured = capsys.readouterr()
        assert 'get_element' in captured.out
        assert 'def get_element' in captured.out


class TestRevealAdapterComponentFiltering:
    """Test component-specific filtering (analyzers, adapters, rules)."""

    def test_filter_analyzers_only(self):
        """Filter to show only analyzers."""
        adapter = RevealAdapter(component='analyzers')
        structure = adapter.get_structure()

        # Should have analyzers
        assert 'analyzers' in structure
        assert len(structure['analyzers']) > 0

        # Should NOT have adapters or rules at top level
        assert 'adapters' not in structure
        assert 'rules' not in structure

    def test_filter_adapters_only(self):
        """Filter to show only adapters."""
        adapter = RevealAdapter(component='adapters')
        structure = adapter.get_structure()

        # Should have adapters
        assert 'adapters' in structure
        assert len(structure['adapters']) > 0

        # Should NOT have analyzers or rules
        assert 'analyzers' not in structure
        assert 'rules' not in structure

    def test_filter_rules_only(self):
        """Filter to show only rules."""
        adapter = RevealAdapter(component='rules')
        structure = adapter.get_structure()

        # Should have rules
        assert 'rules' in structure
        assert len(structure['rules']) > 0

        # Should NOT have analyzers or adapters
        assert 'analyzers' not in structure
        assert 'adapters' not in structure

    def test_filter_case_insensitive(self):
        """Component filtering is case-insensitive."""
        adapter_lower = RevealAdapter(component='analyzers')
        adapter_upper = RevealAdapter(component='ANALYZERS')

        struct_lower = adapter_lower.get_structure()
        struct_upper = adapter_upper.get_structure()

        # Both should filter to analyzers
        assert 'analyzers' in struct_lower
        assert 'analyzers' in struct_upper


class TestRevealAdapterIntegration:
    """Integration tests for reveal:// adapter."""

    def test_full_workflow(self):
        """Test complete inspection workflow."""
        # Initialize
        adapter = RevealAdapter()

        # Get structure
        structure = adapter.get_structure()
        assert structure['metadata']['analyzers_count'] > 0

        # Format as text
        text = adapter.format_output(structure, 'text')
        assert len(text) > 100

        # Format as JSON
        json_out = adapter.format_output(structure, 'json')
        parsed = json.loads(json_out)
        assert parsed['metadata']['analyzers_count'] == structure['metadata']['analyzers_count']

    def test_supported_types(self):
        """_get_supported_types returns file types."""
        adapter = RevealAdapter()
        types = adapter._get_supported_types()

        assert isinstance(types, list)
        # Should find at least some types
        if types:
            assert all(isinstance(t, str) for t in types)


class TestRevealAdapterConfig:
    """Test reveal://config configuration transparency."""

    def test_get_config_returns_dict(self):
        """_get_config returns a dict."""
        adapter = RevealAdapter(component='config')
        config = adapter._get_config()

        assert isinstance(config, dict)

    def test_get_config_has_sections(self):
        """_get_config has all expected sections."""
        adapter = RevealAdapter(component='config')
        config = adapter._get_config()

        assert 'active_config' in config
        assert 'sources' in config
        assert 'metadata' in config
        assert 'precedence_order' in config

    def test_get_config_active_config(self):
        """Active config section has expected fields."""
        adapter = RevealAdapter(component='config')
        config = adapter._get_config()
        active = config['active_config']

        assert 'rules' in active
        assert 'ignore' in active
        assert 'root' in active
        assert 'overrides' in active

    def test_get_config_sources(self):
        """Sources section has expected fields."""
        adapter = RevealAdapter(component='config')
        config = adapter._get_config()
        sources = config['sources']

        assert 'env_vars' in sources
        assert 'custom_config' in sources
        assert 'project_configs' in sources
        assert 'user_config' in sources
        assert 'system_config' in sources

    def test_get_config_metadata(self):
        """Metadata section has expected fields."""
        adapter = RevealAdapter(component='config')
        config = adapter._get_config()
        meta = config['metadata']

        assert 'project_root' in meta
        assert 'working_directory' in meta
        assert 'no_config_mode' in meta
        assert 'env_vars_count' in meta
        assert 'config_files_count' in meta

    def test_get_structure_with_config_component(self):
        """get_structure returns config when component='config'."""
        adapter = RevealAdapter(component='config')
        structure = adapter.get_structure()

        # Should return config structure, not default structure
        assert 'active_config' in structure
        assert 'sources' in structure
        assert 'analyzers' not in structure  # Should not have default structure

    def test_format_config_output_text(self):
        """Config output can be formatted as text."""
        adapter = RevealAdapter(component='config')
        config = adapter._get_config()
        output = adapter.format_output(config, 'text')

        assert isinstance(output, str)
        assert 'Reveal Configuration' in output
        assert 'Overview' in output
        assert 'Configuration Sources' in output
        assert 'Active Configuration' in output
        assert 'Configuration Precedence' in output

    def test_format_config_output_json(self):
        """Config output can be formatted as JSON."""
        adapter = RevealAdapter(component='config')
        config = adapter._get_config()
        output = adapter.format_output(config, 'json')

        # Should be valid JSON
        parsed = json.loads(output)
        assert 'active_config' in parsed
        assert 'sources' in parsed
        assert 'metadata' in parsed

    def test_config_precedence_order(self):
        """Config includes precedence order."""
        adapter = RevealAdapter(component='config')
        config = adapter._get_config()

        precedence = config['precedence_order']
        assert isinstance(precedence, list)
        assert len(precedence) == 7  # Should have 7 levels
        assert any('CLI' in p for p in precedence)
        assert any('Environment' in p for p in precedence)
        assert any('defaults' in p for p in precedence)
