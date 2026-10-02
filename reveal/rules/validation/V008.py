"""V008: Analyzer get_structure signature validation.

Validates that all analyzer get_structure() methods accept **kwargs, and that none
declares head/tail/range. **kwargs prevents a TypeError when the display layer passes
optional parameters. head/tail/range are never passed: the display layer cuts the
result once (FileAnalyzer.cut_structure, BACK-1548), so an analyzer that declares them
slices nothing and reads as if it did.

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

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
import ast

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root
from ...utils.pyparse import parse_python

logger = logging.getLogger(__name__)


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
    """Validate analyzer get_structure signatures: **kwargs, and no head/tail/range."""

    code = "V008"
    message = "Analyzer get_structure() missing **kwargs parameter"
    category = RulePrefix.V
    severity = Severity.HIGH  # High because this causes runtime errors
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check that analyzer get_structure methods accept **kwargs."""
        if not file_path.startswith('reveal://'):
            return []

        detections: List[Detection] = []

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
            content = analyzer_path.read_text(encoding='utf-8')
            tree = parse_python(content, str(analyzer_path))
            return self._find_get_structure_violations(tree, analyzer_path)
        except Exception as e:
            # Don't fail the check if we can't parse the file
            logger.debug("V008.py: skipped after %s: %s", type(e).__name__, e)
            return []

    def _find_get_structure_violations(
        self, tree: ast.AST, analyzer_path: Path
    ) -> List[Detection]:
        """Find all get_structure signature violations in an AST."""
        detections: List[Detection] = []

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

        # head/tail/range are the display layer's cut, never an analyzer's (BACK-1548)
        param_names = [arg.arg for arg in func.args.args + func.args.kwonlyargs]
        slicing = [param for param in ('head', 'tail', 'range') if param in param_names]
        if slicing:
            return self._create_slicing_params_detection(ctx, slicing)

        return None

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
                "def get_structure(self, **kwargs):"
            ),
            context=(
                "Base class FileAnalyzer.get_structure() accepts **kwargs. "
                "Subclasses must maintain this contract (Liskov Substitution Principle)."
            )
        )

    def _create_slicing_params_detection(
        self, ctx: DetectionContext, params: List[str]
    ) -> Detection:
        """Create detection for a get_structure that declares head/tail/range.

        Args:
            ctx: Location context for the detection
            params: The slicing parameter names it declares
        """
        return self.create_detection(
            file_path=str(ctx.analyzer_path),
            line=ctx.line,
            message=f"Class '{ctx.class_name}.get_structure()' declares {', '.join(params)}, "
                    f"which it is never passed",
            suggestion=(
                "Return every item and drop the parameters:\n"
                "def get_structure(self, **kwargs):\n"
                "Name the lists --head means with SLICE_FIELDS, and a no-flag sample with "
                "DEFAULT_HEAD."
            ),
            context=(
                "The display layer cuts get_structure()'s result once and discloses the cut "
                "(FileAnalyzer.cut_structure, BACK-1548); an analyzer never sees --head."
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
