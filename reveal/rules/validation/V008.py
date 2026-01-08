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

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
import ast

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


@dataclass
class DetectionContext:
    """Location context for creating a detection.

    Bundles the common parameters needed to create a detection,
    reducing parameter repetition across detection creator methods.
    """
    line: int
    class_name: str
    analyzer_path: Path


class V008(BaseRule):
    """Validate that all analyzer get_structure methods accept **kwargs."""

    code = "V008"
    message = "Analyzer get_structure() missing **kwargs parameter"
    category = RulePrefix.V
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
        reveal_root = find_reveal_root()
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
        try:
            content = analyzer_path.read_text()
            tree = ast.parse(content)
            return self._find_get_structure_violations(tree, analyzer_path)
        except Exception:
            # Don't fail the check if we can't parse the file
            return []

    def _find_get_structure_violations(
        self, tree: ast.AST, analyzer_path: Path
    ) -> List[Detection]:
        """Find all get_structure signature violations in an AST."""
        detections = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            for func in node.body:
                if not isinstance(func, ast.FunctionDef):
                    continue
                if func.name != 'get_structure':
                    continue

                # Found get_structure method - validate it
                violation = self._validate_signature(func, node.name, analyzer_path)
                if violation:
                    detections.append(violation)

        return detections

    def _validate_signature(
        self, func: ast.FunctionDef, class_name: str, analyzer_path: Path
    ) -> Optional[Detection]:
        """Validate get_structure signature.

        Returns Detection if signature is invalid, None otherwise.
        """
        # Create detection context once
        ctx = DetectionContext(
            line=func.lineno,
            class_name=class_name,
            analyzer_path=analyzer_path
        )

        # Check for **kwargs requirement
        has_kwargs = func.args.kwarg and func.args.kwarg.arg == 'kwargs'
        if not has_kwargs:
            return self._create_missing_kwargs_detection(ctx)

        # Check for required base parameters
        param_names = [arg.arg for arg in func.args.args if arg.arg != 'self']
        missing_params = self._find_missing_base_params(param_names)
        if missing_params:
            return self._create_missing_params_detection(ctx, missing_params)

        return None

    def _find_missing_base_params(self, param_names: List[str]) -> List[str]:
        """Find which required base parameters are missing.

        Args:
            param_names: List of parameter names from function signature

        Returns:
            List of missing parameter names (empty if all present)
        """
        required = ['head', 'tail', 'range']
        return [param for param in required if param not in param_names]

    def _create_missing_kwargs_detection(
        self, ctx: DetectionContext
    ) -> Detection:
        """Create detection for missing **kwargs parameter.

        Args:
            ctx: Location context for the detection
        """
        return self.create_detection(
            file_path=str(ctx.analyzer_path),
            line=ctx.line,
            message=f"Class '{ctx.class_name}.get_structure()' missing **kwargs parameter",
            suggestion=(
                "Update signature to match base class:\n"
                "def get_structure(self, head=None, tail=None, range=None, **kwargs):"
            ),
            context=(
                "Base class FileAnalyzer.get_structure() accepts head/tail/range/**kwargs. "
                "Subclasses must maintain this contract (Liskov Substitution Principle)."
            )
        )

    def _create_missing_params_detection(
        self, ctx: DetectionContext, missing_params: List[str]
    ) -> Detection:
        """Create detection for missing base parameters.

        Args:
            ctx: Location context for the detection
            missing_params: List of parameter names that are missing
        """
        return self.create_detection(
            file_path=str(ctx.analyzer_path),
            line=ctx.line,
            message=f"Class '{ctx.class_name}.get_structure()' missing base parameters: {', '.join(missing_params)}",
            suggestion=(
                "Add base parameters for consistency:\n"
                "def get_structure(self, head=None, tail=None, range=None, **kwargs):"
            ),
            context=(
                "While **kwargs technically accepts these, explicitly declaring "
                "head/tail/range improves clarity and matches base class contract."
            )
        )

    def _get_analyzer_files(self, reveal_root: Path) -> List[Path]:
        """Get all analyzer Python files.

        Returns:
            List of paths to analyzer files
        """
        analyzers_dir = reveal_root / 'analyzers'
        if not analyzers_dir.exists():
            return []

        analyzer_files = []

        # Get all .py files in analyzers directory
        analyzer_files.extend(self._scan_directory_for_analyzers(analyzers_dir))

        # Also check subdirectories (like office/)
        for subdir in analyzers_dir.iterdir():
            if not subdir.is_dir() or subdir.name.startswith('_'):
                continue
            analyzer_files.extend(self._scan_directory_for_analyzers(subdir))

        return analyzer_files

    def _scan_directory_for_analyzers(self, directory: Path) -> List[Path]:
        """Scan a directory for analyzer Python files.

        Args:
            directory: Directory to scan

        Returns:
            List of analyzer file paths (excluding private files)
        """
        files = []
        for file in directory.glob('*.py'):
            if not file.stem.startswith('_'):
                files.append(file)
        return files
