"""V008: Analyzer get_structure signature validation.

Validates that all analyzer get_structure() methods accept **kwargs.
This prevents TypeError when the display layer passes optional parameters.

Example violation:
    - Analyzer: reveal/analyzers/yaml_json.py (JsonAnalyzer)
    - Method: get_structure(self) -> Dict
    - Issue: Missing **kwargs, causes TypeError when outline parameter passed
    - Fix: get_structure(self, **kwargs) -> Dict

Background:
    The display layer (reveal/display/structure.py) passes optional parameters
    like 'outline' to all analyzers. Analyzers must accept **kwargs even if they
    don't use these parameters, to maintain interface compatibility.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import ast
import inspect

from ..base import BaseRule, Detection, RulePrefix, Severity


class V008(BaseRule):
    """Validate that all analyzer get_structure methods accept **kwargs."""

    code = "V008"
    message = "Analyzer get_structure() missing **kwargs parameter"
    category = RulePrefix.M  # Maintainability
    severity = Severity.HIGH  # High because this causes runtime errors
    file_patterns = ['*']  # Runs on any target (checks reveal internals)

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check that analyzer get_structure methods accept **kwargs."""
        detections = []

        # Only run this check for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = self._find_reveal_root()
        if not reveal_root:
            return detections

        # Get all analyzer files
        analyzers = self._get_analyzer_files(reveal_root)

        # Check each analyzer file
        for analyzer_path in analyzers:
            violations = self._check_analyzer_file(analyzer_path)
            detections.extend(violations)

        return detections

    def _check_analyzer_file(self, analyzer_path: Path) -> List[Detection]:
        """Check a single analyzer file for get_structure signature issues."""
        detections = []

        try:
            content = analyzer_path.read_text()
            tree = ast.parse(content)

            # Find all class definitions
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue

                # Check if class has get_structure method
                for item in node.body:
                    if not isinstance(item, ast.FunctionDef):
                        continue
                    if item.name != 'get_structure':
                        continue

                    # Check signature matches base class contract
                    has_kwargs = item.args.kwarg and item.args.kwarg.arg == 'kwargs'

                    # Get parameter names
                    param_names = [arg.arg for arg in item.args.args if arg.arg != 'self']

                    # Check for required base parameters
                    has_head = 'head' in param_names
                    has_tail = 'tail' in param_names
                    has_range = 'range' in param_names

                    # Either has explicit head/tail/range + **kwargs, or just **kwargs (acceptable)
                    if not has_kwargs:
                        detections.append(self.create_detection(
                            file_path=str(analyzer_path),
                            line=item.lineno,
                            message=f"Class '{node.name}.get_structure()' missing **kwargs parameter",
                            suggestion=(
                                f"Update signature to match base class:\n"
                                f"def get_structure(self, head=None, tail=None, range=None, **kwargs):"
                            ),
                            context=(
                                f"Base class FileAnalyzer.get_structure() accepts head/tail/range/**kwargs. "
                                f"Subclasses must maintain this contract (Liskov Substitution Principle)."
                            )
                        ))
                    elif not (has_head and has_tail and has_range):
                        # Has **kwargs but missing explicit base params - warn
                        missing = []
                        if not has_head: missing.append('head')
                        if not has_tail: missing.append('tail')
                        if not has_range: missing.append('range')

                        detections.append(self.create_detection(
                            file_path=str(analyzer_path),
                            line=item.lineno,
                            message=f"Class '{node.name}.get_structure()' missing base parameters: {', '.join(missing)}",
                            suggestion=(
                                f"Add base parameters for consistency:\n"
                                f"def get_structure(self, head=None, tail=None, range=None, **kwargs):"
                            ),
                            context=(
                                f"While **kwargs technically accepts these, explicitly declaring "
                                f"head/tail/range improves clarity and matches base class contract."
                            )
                        ))

        except Exception as e:
            # Don't fail the check if we can't parse the file
            pass

        return detections

    def _find_reveal_root(self) -> Optional[Path]:
        """Find reveal's root directory."""
        # Start from this file's location
        current = Path(__file__).parent.parent.parent

        # Check if we're in the reveal package
        if (current / 'analyzers').exists() and (current / 'rules').exists():
            return current

        # Search up to 5 levels
        for _ in range(5):
            if (current / 'reveal' / 'analyzers').exists():
                return current / 'reveal'
            current = current.parent
            if current == current.parent:  # Reached root
                break

        return None

    def _get_analyzer_files(self, reveal_root: Path) -> List[Path]:
        """Get all analyzer Python files.

        Returns:
            List of paths to analyzer files
        """
        analyzer_files = []
        analyzers_dir = reveal_root / 'analyzers'

        if not analyzers_dir.exists():
            return analyzer_files

        # Get all .py files in analyzers directory
        for file in analyzers_dir.glob('*.py'):
            if file.stem.startswith('_'):
                continue
            analyzer_files.append(file)

        # Also check subdirectories (like office/)
        for subdir in analyzers_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('_'):
                for file in subdir.glob('*.py'):
                    if file.stem.startswith('_'):
                        continue
                    analyzer_files.append(file)

        return analyzer_files
