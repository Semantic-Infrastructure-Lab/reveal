"""Tests for Windows Batch file analyzer."""

import pytest
import tempfile
import os
from reveal.analyzers.batch import BatchAnalyzer


@pytest.fixture
def simple_batch():
    """Create a simple batch file for testing."""
    content = """@echo off
setlocal EnableDelayedExpansion

rem Build script for MyProject
set BUILD_DIR=build
set VERSION=1.0.0

call :setup
call :build
goto :eof

:setup
echo Setting up...
mkdir %BUILD_DIR% 2>nul
exit /b

:build
echo Building version %VERSION%...
exit /b
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as f:
        f.write(content)
        f.flush()
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def empty_batch():
    """Create an empty batch file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as f:
        f.write('@echo off\nrem Empty script\n')
        f.flush()
        yield f.name
    os.unlink(f.name)


class TestBatchStructure:
    """Test structure extraction from batch files."""

    def test_extracts_labels_as_functions(self, simple_batch):
        """Labels should be extracted as functions."""
        analyzer = BatchAnalyzer(simple_batch)
        structure = analyzer.get_structure()

        assert 'functions' in structure
        assert len(structure['functions']) == 2
        assert structure['functions'][0]['name'] == 'setup'
        assert structure['functions'][1]['name'] == 'build'

    def test_extracts_variables(self, simple_batch):
        """SET commands should be extracted as variables."""
        analyzer = BatchAnalyzer(simple_batch)
        structure = analyzer.get_structure()

        assert 'variables' in structure
        assert len(structure['variables']) == 2
        var_names = [v['name'] for v in structure['variables']]
        assert 'BUILD_DIR' in var_names
        assert 'VERSION' in var_names

    def test_extracts_internal_calls(self, simple_batch):
        """Internal subroutine calls should be extracted."""
        analyzer = BatchAnalyzer(simple_batch)
        structure = analyzer.get_structure()

        assert 'internal_calls' in structure
        assert len(structure['internal_calls']) == 2
        call_names = [c['name'] for c in structure['internal_calls']]
        assert ':setup' in call_names
        assert ':build' in call_names

    def test_empty_batch_file(self, empty_batch):
        """Empty batch file should work without errors."""
        analyzer = BatchAnalyzer(empty_batch)
        structure = analyzer.get_structure()

        assert structure['functions'] == []
        assert structure['variables'] == []

    def test_stats_included(self, simple_batch):
        """Statistics should be calculated."""
        analyzer = BatchAnalyzer(simple_batch)
        structure = analyzer.get_structure()

        assert 'stats' in structure
        stats = structure['stats']
        assert stats['has_echo_off'] is True
        assert stats['has_setlocal'] is True
        assert stats['total_lines'] > 0


class TestBatchExtraction:
    """Test element extraction from batch files."""

    def test_extract_label_by_name(self, simple_batch):
        """Should extract label content by name."""
        analyzer = BatchAnalyzer(simple_batch)
        result = analyzer.extract_element('function', 'setup')

        assert result is not None
        assert result['name'] == 'setup'
        assert ':setup' in result['source']
        assert 'echo Setting up' in result['source']

    def test_extract_label_case_insensitive(self, simple_batch):
        """Label extraction should be case-insensitive."""
        analyzer = BatchAnalyzer(simple_batch)
        result = analyzer.extract_element('function', 'SETUP')

        assert result is not None
        assert result['name'] == 'setup'

    def test_extract_nonexistent_label(self, simple_batch):
        """Extracting nonexistent label should return None."""
        analyzer = BatchAnalyzer(simple_batch)
        result = analyzer.extract_element('function', 'nonexistent')

        assert result is None

    def test_extract_with_colon_prefix(self, simple_batch):
        """Extraction should work with or without colon prefix."""
        analyzer = BatchAnalyzer(simple_batch)

        result1 = analyzer.extract_element('function', 'setup')
        result2 = analyzer.extract_element('function', ':setup')

        assert result1 is not None
        assert result2 is not None
        assert result1['source'] == result2['source']


class TestBatchFiltering:
    """Test filtering options for batch files."""

    def test_head_filter(self, simple_batch):
        """Should limit to first N labels."""
        analyzer = BatchAnalyzer(simple_batch)
        structure = analyzer.get_structure(head=1)

        assert len(structure['functions']) == 1
        assert structure['functions'][0]['name'] == 'setup'

    def test_tail_filter(self, simple_batch):
        """Should limit to last N labels."""
        analyzer = BatchAnalyzer(simple_batch)
        structure = analyzer.get_structure(tail=1)

        assert len(structure['functions']) == 1
        assert structure['functions'][0]['name'] == 'build'

    def test_range_filter(self, simple_batch):
        """Should filter labels by range."""
        analyzer = BatchAnalyzer(simple_batch)
        structure = analyzer.get_structure(range=(1, 1))

        assert len(structure['functions']) == 1
        assert structure['functions'][0]['name'] == 'setup'


class TestBatchRegistration:
    """Test analyzer registration."""

    def test_bat_extension_registered(self):
        """The .bat extension should be registered."""
        from reveal.registry import get_analyzer
        analyzer_cls = get_analyzer('/test/file.bat')
        assert analyzer_cls is not None
        assert analyzer_cls.__name__ == 'BatchAnalyzer'

    def test_cmd_extension_registered(self):
        """The .cmd extension should be registered."""
        from reveal.registry import get_analyzer
        analyzer_cls = get_analyzer('/test/file.cmd')
        assert analyzer_cls is not None
        assert analyzer_cls.__name__ == 'BatchAnalyzer'
