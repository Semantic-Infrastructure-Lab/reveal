"""What each import of a file binds a local name to, read from the resolved import analysis.

A consumer that looks a use up by name -- calls' callee resolution (BACK-2553) and its callers index
(BACK-2567) -- asks here instead of resolving imports
itself: the target file is the one the resolution pass found (``ImportStatement.resolved_path``), so
the answer is the one imports:// gives for the same statement. A name bound only by imports that resolved to no file is ``unresolved``: when the
extractor's verdict (``ImportStatement.intra_verdict``, BACK-2550) says outside the tree, no project
function of that name is what a use of it reaches; when it cannot tell (a Python third-party package,
or an in-tree package under a root reveal does not model), only one whose file sits at the module's
path, by its language's rule (``LanguageExtractor.unplaced_module_paths``), can be (BACK-2573). An
import the verdict or its relative spelling puts in the tree is never ``unresolved``: resolution
missing it says nothing about where its names are defined.
"""

import os
from collections import OrderedDict
from pathlib import Path, PurePosixPath
from typing import Any, Dict, FrozenSet, Iterable, NamedTuple, Optional, Set, Tuple, Union

from .types import ImportStatement
from .unused import binds_reliably, bound_name, bound_names
from ...utils.request_cache import in_host_request, register_validated_cache

_PACKAGE_FILES = frozenset({'__init__', 'index', 'mod'})


ModulePath = Tuple[str, ...]  # a module spelling split into its parts ('dagster', '_grpc', 'client')


class Binding(NamedTuple):
    """What an import binds a local name to."""
    target: Optional[str]   # the one file every import binding the name resolved to
    unresolved: bool        # every import binding the name, by the language's own rule, resolved to no file
                            # and may be from outside the tree (not an in-tree verdict or a relative spelling)
    # For an unresolved name, the module paths it may still come from inside the tree: those of a
    # statement whose verdict could not place it (a package root or sys.path entry reveal does not
    # model, as a monorepo's python_modules/dagster). Empty: every statement is outside the tree.
    modules: Tuple[ModulePath, ...] = ()
    # The module path the name is imported from, as the import spells it ('os.path.join' for
    # ``from os.path import join``), when every statement binding it agrees; None otherwise.
    origin: Optional[str] = None


def reaches(binding: Optional[Binding], call: str, caller_file: str, files: Iterable[str]) -> Set[str]:
    """Of ``files`` (where the called name is defined in the project), the ones ``call`` in
    ``caller_file`` can reach given what its qualifier or bare name is bound to: all of them unless
    imports that resolved to no file bind it; then none when they are outside the tree (BACK-2553), and
    only a file at one of their module paths when the verdict could not place them (BACK-2573). A bare
    call to a name its own file defines reaches it (the definition shadows the import). The one rule
    for both directions: callee resolution and the callers index (BACK-2567)."""
    files = set(files)
    if binding is None or not binding.unresolved:
        return files
    if '.' not in call and caller_file in files:
        return files
    return {f for f in files if at_module(f, binding.modules)}


def _origins(stmt: ImportStatement) -> Dict[str, str]:
    """Local name -> the import's spelling of what it binds: a named entry's module and name, an
    aliased or namespace import's module."""
    module = stmt.module_name or ''
    if stmt.import_type == 'default_import':
        return {name: module for name in bound_names(stmt)}
    named = {bound_name(entry): f"{module}.{entry.split(' as ')[0].strip()}"
             for entry in stmt.imported_names if entry != '*'}
    if not named and (stmt.alias or stmt.import_type == 'namespace_import'):
        return {name: module for name in bound_names(stmt)}
    return named


def at_module(file_path: str, modules: Iterable[ModulePath]) -> bool:
    """Whether ``file_path`` is where one of ``modules`` would sit: its path without the extension
    (and without a package's ``__init__``/``index``/``mod``) ends with the module's parts; for a
    language whose package is a directory (Go), its directory does."""
    path = PurePosixPath(file_path.replace('\\', '/'))
    parts = tuple(path.with_suffix('').parts)
    if _package_is_directory(path.suffix):
        forms = [parts[:-1]]
    else:
        forms = [parts, parts[:-1]] if parts and parts[-1] in _PACKAGE_FILES else [parts]
    return any(len(form) >= len(module) and form[-len(module):] == module
               for module in modules for form in forms)


def _package_is_directory(suffix: str) -> bool:
    from .base import extractor_class
    cls = extractor_class(suffix)
    return bool(cls and cls.package_is_directory)


def _unplaced_module_paths(stmt: ImportStatement) -> Tuple[ModulePath, ...]:
    """Where an unplaced ``stmt`` (unknown verdict) may sit: its language's own rule
    (``LanguageExtractor.unplaced_module_paths``); none for a file no extractor reads."""
    from .base import get_extractor
    extractor = get_extractor(Path(stmt.file_path))
    return extractor.unplaced_module_paths(stmt) if extractor is not None else ()


def _bound_target(stmt: ImportStatement, name: str) -> Optional[str]:
    """The file the name ``name`` that ``stmt`` binds is: its resolved file, except in Python, where a
    statement resolves to its first target. ``import a.b`` binds ``a``, the package, while it resolved to
    ``a/b.py``: then ``a/__init__.py`` (None for a namespace package). ``from pkg import mod`` resolved to
    ``pkg/__init__.py`` and binds ``mod`` to the submodule ``pkg/mod.py`` when there is one (BACK-2574)."""
    resolved = stmt.resolved_path
    if resolved is None:
        return None
    if resolved.suffix not in ('.py', '.pyi'):
        return str(resolved)
    if stmt.imported_names and resolved.stem == '__init__':
        return _submodule(stmt, name, resolved)
    depth = (stmt.module_name or '').count('.')
    if depth and not stmt.imported_names and not stmt.alias:
        return _top_package(resolved, depth)
    return str(resolved)


def _submodule(stmt: ImportStatement, name: str, package_init: Path) -> str:
    """``from pkg import mod``: the submodule ``mod`` names, else the package's __init__.py."""
    entry = next((e for e in stmt.imported_names if bound_name(e) == name), None)
    member = entry.split(' as ')[0].strip() if entry else ''
    for candidate in (package_init.parent / f'{member}.py', package_init.parent / member / '__init__.py'):
        if member and candidate.is_file():
            return str(candidate)
    return str(package_init)


def _top_package(resolved: Path, depth: int) -> Optional[str]:
    """``import a.b`` resolved to a/b.py (or a/b/__init__.py): a/__init__.py, None for a namespace package."""
    package = resolved.parent.parent if resolved.stem == '__init__' else resolved.parent
    for _ in range(depth - 1):
        package = package.parent
    init = package / '__init__.py'
    return str(init) if init.is_file() else None


def file_bindings(imports: Iterable[ImportStatement]) -> Dict[str, Binding]:
    """Local name -> binding, from one file's resolved import statements. A name names a file only
    when every statement that binds it names the same one, and is unresolved only when none of them
    resolved; a bare import whose bound name is a guess (``binds_reliably``: C ``#include <array>``
    binds no ``array``) is never unresolved. Such an import still names its file when it resolved
    in-tree (Zig ``const config = @import("config.zig")``), which only ever narrows candidates."""
    bindings: Dict[str, Binding] = {}
    for stmt in imports:
        unresolved = stmt.resolved_path is None and binds_reliably(stmt) and _not_in_tree(stmt)
        modules = _unplaced_module_paths(stmt) if unresolved and stmt.intra_verdict is None else ()
        origins = _origins(stmt)
        for name in bound_names(stmt):
            target = _bound_target(stmt, name)
            seen = bindings.get(name)
            origin = origins.get(name)
            # Several imports binding one name (Java `import org.a.X` and `import org.b.Y` both
            # bind the guess `org`) name a file only when they agree on it.
            bindings[name] = (Binding(target, unresolved, modules, origin) if seen is None else
                              Binding(seen.target if seen.target == target else None,
                                      seen.unresolved and unresolved,
                                      seen.modules + modules if seen.unresolved and unresolved else (),
                                      seen.origin if seen.origin == origin else None))
    return bindings


def _not_in_tree(stmt: ImportStatement) -> bool:
    """Whether an import resolution placed in no file may be from outside the tree: not when the
    extractor's verdict puts it in the tree, nor when its spelling is relative (Rust ``crate::``,
    ``super::``; Python ``from . import``): resolution missed it (a crate with no Cargo.toml), and
    that is no claim about where its names are defined."""
    return stmt.intra_verdict is not True and not stmt.is_relative


class ProjectBindings:
    """The import bindings of the files at one target (a directory or a file), from the import
    analysis imports:// builds for it: ``service.project_scope``, the project root the shared climb
    chooses, focused on the target (BACK-2565), or a cached whole-root build. Built on the first
    lookup, so a consumer that never asks pays nothing. A file the analysis does not hold (past the
    scan's file cap, or one no import extractor reads) has no bindings: nothing is claimed about
    its names."""

    def __init__(self, target: Optional[Path]) -> None:
        self._target = target
        self._files: Dict[str, Dict[str, Binding]] = {}
        self._extractions: Optional[Dict[str, Any]] = None
        self._bound_names: Dict[str, FrozenSet[str]] = {}
        self._scope_root: Optional[str] = None

    def get(self, file_path: str, name: str) -> Optional[Binding]:
        """What ``name`` is bound to in ``file_path``: None unless one of the file's own imports binds
        it, which its import extraction answers without the project's analysis, so a file (or a
        whole query) whose calls go through no import never builds it. Same answer as
        ``of(file_path).get(name)``: the analysis binds from the same statements."""
        if file_path not in self._bound_names:
            self._bound_names[file_path] = _names_bound_in(file_path, self._root())
        if name not in self._bound_names[file_path]:
            return None
        return self.of(file_path).get(name)

    def _root(self) -> Optional[str]:
        """The tree whose stamp keeps this target's remembered bound names: the target directory,
        the one the callers index is kept for, spelled as given (no project climb: a query whose
        calls go through no import walks nothing, 3af89992). None for a file target."""
        if self._scope_root is None and self._target is not None and self._target.is_dir():
            self._scope_root = str(self._target)
        return self._scope_root

    def _by_file(self) -> Dict[str, Any]:
        """The analysis' extractions keyed by absolute path: its root may be spelled '..' while the
        consumer walked '.', so the two spellings of one file must meet."""
        if self._extractions is None:
            self._extractions = {}
            if self._target is not None:
                from . import service
                analysis = service.analyze(service.project_scope(self._target)).analysis
                self._extractions = {_absolute(path): extraction
                                     for path, extraction in analysis.extractions.items()}
        return self._extractions

    def of(self, file_path: str) -> Dict[str, Binding]:
        """Local name -> binding for one file, however the consumer spells its path."""
        if file_path not in self._files:
            extraction = self._by_file().get(_absolute(file_path))
            self._files[file_path] = file_bindings(extraction.imports) if extraction is not None else {}
        return self._files[file_path]


# Target directory -> absolute path -> the names that file's import statements bind, kept across
# host requests while that tree is unchanged (register_validated_cache, as the callers index is). The extraction's own in-process layer is emptied at every request (BACK-2083)
# and the disk layer may be off, so without this every ?callers= query re-parsed every file holding a
# call to the name (BACK-2579).
_BOUND_NAMES: 'OrderedDict[str, Dict[str, FrozenSet[str]]]' = OrderedDict()
_BOUND_NAMES_ROOTS = 4


def _evict_bound_names(root: str) -> None:
    _BOUND_NAMES.pop(root, None)


register_validated_cache(__name__ + '.bound_names', _BOUND_NAMES, _evict_bound_names)


def clear_bound_names() -> None:
    """Forget every remembered root (tests)."""
    _BOUND_NAMES.clear()


def _names_bound_in(file_path: str, root: Optional[str]) -> FrozenSet[str]:
    """Every local name the file's own import statements bind (no resolution). Inside a host
    request, a file under ``root`` is read once while the root's tree is unchanged; an extraction
    its content did not decide (``ImportExtraction.cacheable``) is not kept."""
    from .base import get_extractor
    path = Path(file_path)
    extractor = get_extractor(path)
    if extractor is None:
        return frozenset()
    key = _absolute(path)
    kept_at = root if root is not None and in_host_request() and _under(key, _absolute(root)) else None
    remembered = _BOUND_NAMES.get(kept_at) if kept_at is not None else None
    if remembered is not None and key in remembered:
        return remembered[key]
    try:
        statements = extractor.extract_imports(path)
    except OSError:
        return frozenset()
    names = frozenset(name for stmt in statements for name in bound_names(stmt))
    if kept_at is not None and extractor.analysis.cacheable:
        _BOUND_NAMES.setdefault(kept_at, {})[key] = names
        _BOUND_NAMES.move_to_end(kept_at)
        while len(_BOUND_NAMES) > _BOUND_NAMES_ROOTS:
            _BOUND_NAMES.popitem(last=False)
    return names


def _under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives
        return False


def _absolute(path: Union[str, Path]) -> str:
    return os.path.normcase(os.path.abspath(path))
