"""Tests for --severity filtering in run_pattern_detection (BACK-042)."""

import sys
import io
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.rules.base import Detection, Severity


def _make_detection(severity: Severity, rule_code: str = 'B001') -> Detection:
    """Create a minimal Detection with the given severity."""
    return Detection(
        file_path='example.py',
        line=1,
        rule_code=rule_code,
        message='test issue',
        severity=severity,
    )


def _make_args(severity=None, select=None, ignore=None, no_group=False):
    """Build a minimal args namespace for run_pattern_detection."""
    args = Mock()
    args.select = select
    args.ignore = ignore
    args.no_group = no_group
    args.severity = severity
    return args


class TestSeverityFilter:
    """Tests for severity filtering in run_pattern_detection (BACK-042)."""

    def _run_with_detections(self, detections, severity_arg):
        """Helper: call run_pattern_detection with mocked detections and return output."""
        from reveal.checks import run_pattern_detection

        mock_analyzer = Mock()
        mock_analyzer.get_structure.return_value = {}
        mock_analyzer.content = 'x = 1'

        args = _make_args(severity=severity_arg)

        with patch('reveal.rules.RuleRegistry.check_file', return_value=detections):
            with patch('reveal.checks._is_generated_file', return_value=False):
                with patch('reveal.checks.print_breadcrumbs'):
                    captured = io.StringIO()
                    with patch('builtins.print', side_effect=lambda *a, **kw: captured.write(' '.join(str(x) for x in a) + '\n')):
                        run_pattern_detection(mock_analyzer, 'example.py', 'text', args)
        return captured.getvalue()

    def test_no_severity_arg_shows_all(self):
        """Without --severity, all detections are shown."""
        detections = [
            _make_detection(Severity.LOW, 'L001'),
            _make_detection(Severity.MEDIUM, 'M001'),
            _make_detection(Severity.HIGH, 'H001'),
        ]
        output = self._run_with_detections(detections, None)
        assert 'L001' in output
        assert 'M001' in output
        assert 'H001' in output

    def test_severity_high_filters_low_medium(self):
        """--severity high shows only HIGH and CRITICAL."""
        detections = [
            _make_detection(Severity.LOW, 'L001'),
            _make_detection(Severity.MEDIUM, 'M001'),
            _make_detection(Severity.HIGH, 'H001'),
            _make_detection(Severity.CRITICAL, 'C001'),
        ]
        output = self._run_with_detections(detections, 'high')
        assert 'L001' not in output
        assert 'M001' not in output
        assert 'H001' in output
        assert 'C001' in output

    def test_severity_medium_filters_low(self):
        """--severity medium shows MEDIUM, HIGH, and CRITICAL but not LOW."""
        detections = [
            _make_detection(Severity.LOW, 'L001'),
            _make_detection(Severity.MEDIUM, 'M001'),
            _make_detection(Severity.HIGH, 'H001'),
        ]
        output = self._run_with_detections(detections, 'medium')
        assert 'L001' not in output
        assert 'M001' in output
        assert 'H001' in output

    def test_severity_critical_filters_all_but_critical(self):
        """--severity critical shows only CRITICAL."""
        detections = [
            _make_detection(Severity.LOW, 'L001'),
            _make_detection(Severity.MEDIUM, 'M001'),
            _make_detection(Severity.HIGH, 'H001'),
            _make_detection(Severity.CRITICAL, 'C001'),
        ]
        output = self._run_with_detections(detections, 'critical')
        assert 'L001' not in output
        assert 'M001' not in output
        assert 'H001' not in output
        assert 'C001' in output

    def test_severity_low_shows_all(self):
        """--severity low shows all detections (nothing filtered)."""
        detections = [
            _make_detection(Severity.LOW, 'L001'),
            _make_detection(Severity.CRITICAL, 'C001'),
        ]
        output = self._run_with_detections(detections, 'low')
        assert 'L001' in output
        assert 'C001' in output

    def test_severity_invalid_emits_warning(self, capsys):
        """Invalid --severity value emits a stderr warning and shows all detections."""
        from reveal.checks import run_pattern_detection

        detections = [_make_detection(Severity.HIGH, 'H001')]
        mock_analyzer = Mock()
        mock_analyzer.get_structure.return_value = {}
        mock_analyzer.content = 'x = 1'
        args = _make_args(severity='super-high')

        with patch('reveal.rules.RuleRegistry.check_file', return_value=detections):
            with patch('reveal.checks._is_generated_file', return_value=False):
                with patch('reveal.checks.print_breadcrumbs'):
                    run_pattern_detection(mock_analyzer, 'example.py', 'text', args)

        err = capsys.readouterr().err
        assert 'super-high' in err
        assert 'low' in err.lower() or 'valid' in err.lower()

    def test_severity_case_insensitive(self):
        """--severity accepts uppercase and mixed case."""
        detections = [
            _make_detection(Severity.LOW, 'L001'),
            _make_detection(Severity.HIGH, 'H001'),
        ]
        output = self._run_with_detections(detections, 'HIGH')
        assert 'L001' not in output
        assert 'H001' in output

    def test_severity_parser_accepts_flag(self):
        """--severity flag is registered in the argument parser."""
        from reveal.cli.parser import create_argument_parser
        parser = create_argument_parser('test')
        args = parser.parse_args(['example.py', '--check', '--severity', 'high'])
        assert args.severity == 'high'

    def test_severity_parser_default_none(self):
        """--severity defaults to None when not specified."""
        from reveal.cli.parser import create_argument_parser
        parser = create_argument_parser('test')
        args = parser.parse_args(['example.py', '--check'])
        assert args.severity is None
