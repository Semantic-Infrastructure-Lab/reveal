"""Import resolution - map module names to file paths.

Handles Python's import resolution logic:
- Relative imports (./utils, ../models)
- Absolute imports (mypackage.utils)
- Package imports (mypackage.__init__)
- Namespace packages (PEP 420)
"""

from pathlib import Path
from typing import List, Optional

from .types import ImportStatement


def resolve_python_import(
    import_stmt: ImportStatement,
    base_path: Path,
    search_paths: Optional[List[Path]] = None
) -> Optional[Path]:
    """Resolve import statement to actual file path.

    Args:
        import_stmt: Import to resolve
        base_path: Directory containing the importing file
        search_paths: Additional paths to search (like sys.path)

    Returns:
        Resolved file path, or None if not found
    """
    if import_stmt.is_relative:
        return _resolve_relative(import_stmt, base_path)
    else:
        return _resolve_absolute(import_stmt, base_path, search_paths or [])


def _resolve_relative(import_stmt: ImportStatement, base_path: Path) -> Optional[Path]:
    """Resolve relative import (from . import X, from .. import Y).

    Python relative imports:
        from . import utils       -> ./utils.py
        from .. import models     -> ../models.py
        from ..models import User -> ../models.py or ../models/__init__.py
    """
    # Navigate up the directory tree according to the import level.
    # level=1 means '.', level=2 means '..', etc.
    parts = import_stmt.module_name.split('.') if import_stmt.module_name else []
    target_path = base_path
    for _ in range(max(0, import_stmt.level - 1)):
        target_path = target_path.parent

    if not parts:
        # Pure package-relative: `from . import X` or `from . import X, Y, Z`.
        # Each imported name may be a sibling module (X.py) or a name defined in
        # __init__.py.  Try submodule resolution first so that `from . import refs`
        # in adapter.py resolves to refs.py, not __init__.py — the latter creates
        # false-positive cycle edges __init__.py → adapter.py → __init__.py.
        # Note: aliased imports like `from . import query as q` produce
        # imported_names = ['query as q']; strip the alias before resolving.
        for raw_name in import_stmt.imported_names:
            name = raw_name.split()[0]  # 'query as q' → 'query'
            mod_file = target_path / f"{name}.py"
            if mod_file.exists():
                return mod_file
            pkg_init = target_path / name / "__init__.py"
            if pkg_init.exists():
                return pkg_init
        # No imported name matched a submodule — the name lives in __init__.py.
        init = target_path / "__init__.py"
        return init if init.exists() else None

    # Descend the *full* dotted module path, not just its first segment:
    # `from .helpers.typing import X` depends on helpers/typing.py, not
    # helpers/__init__.py. The old parts[0]-only lookup stopped at the first
    # package and silently mis-targeted every multi-segment relative import
    # (helpers/__init__.py absorbed the edge, so the real module's fan-in was
    # undercounted). _try_resolve_module handles the single-part case
    # identically (module.py -> package/__init__.py -> namespace dir).
    return _try_resolve_module(target_path, parts)


def _resolve_absolute(
    import_stmt: ImportStatement,
    base_path: Path,
    search_paths: List[Path]
) -> Optional[Path]:
    """Resolve absolute import (import os, from mypackage import utils).

    Search order:
    1. Current directory (for local packages)
    2. Additional search paths (project root, etc.)
    3. Return None for stdlib/external packages (we don't track those)
    """
    module_parts = import_stmt.module_name.split('.')

    # Build search paths: current dir + provided paths.  A Python 3 absolute
    # import never consults the importing file's own *package* directory (only
    # sys.path roots): when base_path is a package interior (`__init__.py`
    # present), searching it shadows stdlib/third-party names with a same-named
    # sibling module — `from typing import X` in a package that also holds a
    # `typing.py` would resolve to that sibling, a false-positive edge that
    # breaks the "never false positives" invariant. Only treat base_path as a
    # search root in the rootless single-dir fallback (no __init__.py), where
    # it legitimately stands in for the project root.
    if (base_path / "__init__.py").exists():
        all_paths = list(search_paths)
    else:
        all_paths = [base_path] + list(search_paths)

    for search_path in all_paths:
        # Try to resolve as module file or package
        resolved = _try_resolve_module(search_path, module_parts)
        if resolved:
            return resolved

    # Not found in any search path - likely stdlib or external package
    return None


def _try_resolve_module(base: Path, parts: List[str]) -> Optional[Path]:
    """Try to resolve module parts to a file under base path.

    Examples:
        ['mypackage', 'utils'] ->
            1. mypackage/utils.py
            2. mypackage/utils/__init__.py
            3. mypackage/utils/ (namespace package)
    """
    if not parts:
        return None

    # Single module: 'utils' -> utils.py or utils/__init__.py
    if len(parts) == 1:
        module_file = base / f"{parts[0]}.py"
        if module_file.exists():
            return module_file

        package_init = base / parts[0] / "__init__.py"
        if package_init.exists():
            return package_init

        package_dir = base / parts[0]
        if package_dir.is_dir():
            return package_dir

        return None

    # Nested module: 'mypackage.utils' -> mypackage/utils.py
    first = parts[0]
    rest = parts[1:]

    # Check if first part is a package directory
    package_dir = base / first
    if not package_dir.is_dir():
        return None

    # Recursively resolve remaining parts
    return _try_resolve_module(package_dir, rest)


def resolve_python_from_import_submodules(
    import_stmt: ImportStatement,
    base_path: Path,
    search_paths: Optional[List[Path]] = None,
) -> List[Path]:
    """Resolve the submodule files pulled in by ``from pkg import name`` (BACK-542).

    ``resolve_python_import`` resolves only ``import_stmt.module_name`` — for
    ``from homeassistant.helpers import intent`` that is ``homeassistant.helpers``,
    which resolves to ``helpers/__init__.py`` (the package), never to
    ``helpers/intent.py``. But ``from pkg import intent`` (with ``intent.foo()``
    usage) executes and depends on ``pkg/intent.py`` when ``intent`` is a
    submodule — one of the most common Python import idioms. This returns those
    submodule files so the dependency graph records the real edge.

    Only ``from`` imports whose ``pkg`` resolves to a *package directory* yield
    submodules; ``from pkg.mod import foo`` (``mod.py`` is a module, ``foo`` a
    name inside it) yields nothing here, correctly. Names that don't match a
    sibling ``.py``/package are attributes of ``__init__.py`` and are already
    covered by the primary resolution.
    """
    if import_stmt.import_type != 'from_import':
        return []

    pkg_dir = _from_import_package_dir(import_stmt, base_path, search_paths or [])
    if pkg_dir is None:
        return []

    targets: List[Path] = []
    for raw_name in import_stmt.imported_names:
        name = raw_name.split()[0]  # 'intent as i' → 'intent'
        if not name or name == '*':
            continue
        submodule = pkg_dir / f"{name}.py"
        if submodule.exists():
            targets.append(submodule)
            continue
        sub_pkg_init = pkg_dir / name / "__init__.py"
        if sub_pkg_init.exists():
            targets.append(sub_pkg_init)
    return targets


def _from_import_package_dir(
    import_stmt: ImportStatement,
    base_path: Path,
    search_paths: List[Path],
) -> Optional[Path]:
    """Return the package directory a ``from <pkg> import ...`` resolves names in.

    ``None`` when ``pkg`` isn't an in-tree package directory (external/stdlib,
    or a plain module rather than a package).
    """
    parts = import_stmt.module_name.split('.') if import_stmt.module_name else []

    if import_stmt.is_relative:
        target = base_path
        for _ in range(max(0, import_stmt.level - 1)):
            target = target.parent
        for part in parts:
            target = target / part
        return target if target.is_dir() else None

    if not parts:
        return None
    # Same package-interior guard as _resolve_absolute: a `from typing import X`
    # whose base_path package also holds a `typing/` dir must not shadow the
    # stdlib name via the importer's own directory.
    if (base_path / "__init__.py").exists():
        roots = list(search_paths)
    else:
        roots = [base_path] + list(search_paths)
    for search_path in roots:
        candidate = search_path
        for part in parts:
            candidate = candidate / part
        if candidate.is_dir():
            return candidate
    return None


__all__ = [
    'resolve_python_import',
    'resolve_python_from_import_submodules',
]
