"""I007: Declared dependency never imported anywhere in the project.

BACK-1191 (external wishlist, B-family manifest-reconciliation ask).
Dead-dependency detector: a manifest entry with zero corresponding
import/use anywhere in the project is unused supply-chain surface with no
benefit -- the "declared but never used" half of the reconciliation.

Triggered on the manifest file itself, not on every source file --
declared-but-unused is a project-wide fact, not a per-file one. Mirrors
I002's established pattern for this shape: a per-file `check()` call that
builds (and caches, via `_dep_reconciliation._scan_project_imports`) a
whole-project result, keyed off the file that happens to trigger it.

Deliberately Python + Rust only for this first pass -- see
`_dep_reconciliation`'s module docstring for why Ruby (Gemfile.lock is a
*resolved*, transitively-inclusive set, not a *declared* one) and other
languages (no declared-dependency inventory built yet) are out of scope
here.

KNOWN LIMITATION, not a bug: a dependency that's used but never `import`ed
-- a CLI-only dev tool (black, ruff), or a pytest/plugin activated by
config/discovery rather than an explicit import (pytest-cov, pytest-xdist)
-- reads as "declared but never imported" because, narrowly, that's true;
whether it's *used* is a broader question this rule doesn't attempt
(cross-referencing entry_points/console_scripts and CLI invocation would
be a distinct, larger feature). Dogfooded live against reveal's own
pyproject.toml (BACK-1191): alongside that expected class, it also
correctly caught genuinely dead entries (`lxml`, `rich` -- never imported
anywhere in the tree; `tree-sitter` -- only `tree_sitter_language_pack`,
a different declared dependency, is ever imported).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ._dep_reconciliation import (
    _TraversalFailure, _directory_disclosure, python_declared_unused, rust_declared_unused,
)

logger = logging.getLogger(__name__)


class I007(BaseRule):
    """Detect manifest-declared dependencies never imported anywhere in the
    project (Python, Rust)."""

    code = "I007"
    message = "Declared dependency never imported anywhere in the project"
    category = RulePrefix.I
    severity = Severity.LOW
    file_patterns = ['pyproject.toml', 'requirements.txt', 'Cargo.toml']
    version = "1.0.0"

    # BACK-432's file_patterns-token inference doesn't recognize bare
    # manifest filenames (no language-carrying extension to key off) --
    # this rule's real language coverage is Python + Rust, both tier1, so
    # state it explicitly rather than read back as an empty/unverified badge.
    verified_languages = ['python', 'rust']

    def check(
        self,
        file_path: str,
        structure: Optional[Dict[str, Any]],
        content: str,
    ) -> List[Detection]:
        path = Path(file_path).resolve()
        try:
            if path.name == 'Cargo.toml':
                return self._check_rust(path)
            return self._check_python(path)
        except Exception as e:  # boundary-ok: broad-except -- manifest parsing and the project-wide import scan read arbitrary user files and call tree-sitter extractors (no enumerable error set); one manifest must not end the run, and it is recorded as this rule's unavailable outcome with the manifest as subject
            logger.warning(f"I007: failed to analyze {file_path}: {e}")
            return self.unavailable(f"dependency analysis failed: {type(e).__name__}: {e}", str(path))

    def _note_skipped_sources(self, result, manifest_path: Path) -> None:
        """Source files whose imports could not be extracted may be the ones that use a
        dependency reported as unused: record that the answer can contain false positives."""
        if result.skipped:
            shown = ', '.join(result.skipped[:3])
            more = f" (+{len(result.skipped) - 3} more)" if len(result.skipped) > 3 else ''
            self.unavailable(
                f"{len(result.skipped)} source file(s) could not be fully scanned for imports "
                f"({shown}{more}); dependencies reported as unused may be used there",
                str(manifest_path))

    def _check_python(self, manifest_path: Path) -> List[Detection]:
        # requirements.txt and pyproject.toml are unioned into one inventory
        # (BACK-1189) -- report from pyproject.toml when both exist in the
        # same project so a dependency isn't flagged twice.
        if manifest_path.name == 'requirements.txt' and (manifest_path.parent / 'pyproject.toml').exists():
            return []
        failures: List[_TraversalFailure] = []
        result = python_declared_unused(manifest_path.parent, on_traversal_failure=failures.append)
        self._note_skipped_sources(result, manifest_path)
        self._note_directory_sources(failures, manifest_path)
        unused = result.unused
        return [
            self.create_detection(
                file_path=str(manifest_path),
                line=1,
                column=1,
                suggestion=f"Remove unused dependency `{name}`, or verify it's actually used under a different import name reveal doesn't recognize",
                context=f"declared dependency never imported: {name}",
            )
            for name in sorted(unused)
        ]

    def _check_rust(self, manifest_path: Path) -> List[Detection]:
        failures: List[_TraversalFailure] = []
        result = rust_declared_unused(manifest_path.parent, on_traversal_failure=failures.append)
        self._note_skipped_sources(result, manifest_path)
        self._note_directory_sources(failures, manifest_path)
        unused = result.unused
        return [
            self.create_detection(
                file_path=str(manifest_path),
                line=1,
                column=1,
                suggestion=f"Remove unused crate `{name}`, or verify it's actually used under a different name reveal doesn't recognize",
                context=f"declared dependency never used: {name}",
            )
            for name in sorted(unused)
        ]

    def _note_directory_sources(self, failures: List[_TraversalFailure], manifest_path: Path) -> None:
        language = 'Rust' if manifest_path.name == 'Cargo.toml' else 'Python'
        message = _directory_disclosure(manifest_path.parent, failures, language)
        if message is not None:
            self.unavailable(message, str(manifest_path))
