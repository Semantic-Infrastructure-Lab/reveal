"""I008: Imported package not declared in the project manifest.

BACK-1191 (external wishlist, B-family manifest-reconciliation ask).
Undeclared/implicit-dependency detector -- an import resolved as external
(not stdlib, not intra-project) whose name doesn't appear anywhere in the
project's declared/available dependency inventory breaks on a clean
install even though it works locally (something else in the environment
happens to provide it).

Per-file, unlike I007: each import statement is independently checkable
against the project's manifest inventory, no whole-project aggregation
needed.

Stays silent (no detections) whenever the project has *no* declared-
dependency signal at all (empty inventory) -- flagging every external
import as "undeclared" in that case would be pure noise, not a finding;
mirrors `is_intra_project_import`'s own honest-decline design (BACK-1189).

Python + Rust only for this first pass -- both have a vetted, maintained
stdlib name list (`STDLIB_MODULES`, `_RUST_STD_CRATES`) to filter out
before flagging anything, which is the precondition for this rule being
safe rather than noisy. Ruby has no such list in reveal yet (`require
'net/http'`, `require 'digest/md5'`, etc. are stdlib but namespaced, so a
naive "not in the gem inventory" check would misfire on stdlib) -- adding
Ruby needs a real stdlib require-name list first, not a path-shape guess.

Python test files are skipped entirely (`is_test_dir`) -- dogfooded live on
reveal's own ~950-file corpus, every single Python finding under `tests/`
was pytest's `from conftest import X` sibling-import convention (resolved
via pytest's rootdir sys.path insertion, invisible to
`_python_project_inventory`'s local-package detection, which only looks at
`__init__.py` packages and top-level modules). Not a partial fix -- an
actually undeclared third-party import in test code is also a much weaker
DD signal than the same thing in application code, so this is a deliberate
scope cut, not just noise suppression.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports.base import get_extractor
from ...utils.path_utils import is_test_dir, resolve_project_root
from . import STDLIB_MODULES
from ._dep_reconciliation import PY_IMPORT_TO_DIST_ALIASES

logger = logging.getLogger(__name__)


class I008(BaseRule):
    """Detect imports resolved as external but absent from the project's
    declared-dependency manifest (Python, Rust)."""

    code = "I008"
    message = "Import not declared in the project manifest"
    category = RulePrefix.I
    severity = Severity.LOW
    file_patterns = ['.py', '.rs']
    version = "1.0.0"

    def check(
        self,
        file_path: str,
        structure: Optional[Dict[str, Any]],
        content: str,
    ) -> List[Detection]:
        path = Path(file_path)
        ext = path.suffix.lower()
        try:
            if ext == '.py':
                return self._check_python(path)
            if ext == '.rs':
                return self._check_rust(path)
        except Exception as e:
            logger.warning(f"I008: failed to analyze {file_path}: {e}")
        return []

    def _extractor_imports(self, path: Path):
        extractor = get_extractor(path)
        if extractor is None:
            return None
        imports = extractor.extract_imports(path)
        if getattr(extractor, 'parse_failed', False):
            return None
        return imports

    def _check_python(self, path: Path) -> List[Detection]:
        from ...analyzers.imports.python import _python_project_inventory, _normalize_dist_name

        if any(is_test_dir(p) for p in path.parts):
            return []

        imports = self._extractor_imports(path)
        if not imports:
            return []
        project_root = resolve_project_root(path.parent, python_init_chain=True)
        if project_root is None:
            return []
        local_names, external_names = _python_project_inventory(project_root)
        if not external_names:
            return []  # no declared-dependency signal at all -- stay silent

        detections: List[Detection] = []
        for stmt in imports:
            if stmt.is_relative or stmt.level > 0:
                continue
            top_level = stmt.module_name.split('.')[0]
            if not top_level or top_level in STDLIB_MODULES or top_level in local_names:
                continue
            norm = _normalize_dist_name(top_level)
            if norm in external_names:
                continue
            alias_dist = PY_IMPORT_TO_DIST_ALIASES.get(norm)
            if alias_dist and alias_dist in external_names:
                continue
            detections.append(self.create_detection(
                file_path=str(path),
                line=stmt.line_number,
                column=1,
                suggestion=f"Add `{top_level}` to the project's declared dependencies, or verify it's provided some other way (stdlib alias reveal doesn't know, vendored, etc.)",
                context=f"import not found in manifest: {stmt.module_name}",
            ))
        return detections

    def _check_rust(self, path: Path) -> List[Detection]:
        from ...analyzers.imports.rust import _rust_crate_inventory, _RUST_STD_CRATES

        extractor = get_extractor(path)
        if extractor is None:
            return []
        imports = extractor.extract_imports(path)
        if getattr(extractor, 'parse_failed', False):
            return []
        crate_root = extractor._find_cargo_root(path.parent)
        if crate_root is None:
            return []
        local_names, external_names = _rust_crate_inventory(crate_root)
        if not external_names:
            return []

        detections: List[Detection] = []
        for stmt in imports:
            if stmt.is_relative:
                continue
            top_level = stmt.module_name.split('::')[0]
            if not top_level or top_level in _RUST_STD_CRATES or top_level in local_names:
                continue
            if top_level in external_names:
                continue
            detections.append(self.create_detection(
                file_path=str(path),
                line=stmt.line_number,
                column=1,
                suggestion=f"Add `{top_level}` to Cargo.toml's [dependencies], or verify it's provided via a workspace-inherited dependency reveal doesn't see",
                context=f"use not found in manifest: {stmt.module_name}",
            ))
        return detections
