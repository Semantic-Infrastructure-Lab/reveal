"""What each import of a file binds a local name to, read from the resolved import analysis.

A consumer that looks a use up by name -- calls' callee resolution (BACK-2553), ast://'s
``resolved_calls`` (BACK-2566) -- asks here instead of resolving imports itself: the target file is the one the resolution pass found
(``ImportStatement.resolved_path``), so the answer is the one imports:// gives for the same
statement. A name bound only by imports that resolved to no file is ``unresolved``: when the
extractor's verdict (``ImportStatement.intra_verdict``, BACK-2550) says outside the tree, no project
function of that name is what a use of it reaches; when it cannot tell (a Python third-party package,
or an in-tree package under a root reveal does not model), only one whose file sits at the module's
path can be (BACK-2573).
"""

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, NamedTuple, Optional, Tuple, Union

from .types import ImportStatement
from .unused import binds_reliably, bound_name, bound_names

_SEPARATORS = re.compile(r'[./\\:]+')
_PACKAGE_FILES = frozenset({'__init__', 'index', 'mod'})


ModulePath = Tuple[str, ...]  # a module spelling split into its parts ('dagster', '_grpc', 'client')


class Binding(NamedTuple):
    """What an import binds a local name to."""
    target: Optional[str]   # the one file every import binding the name resolved to
    unresolved: bool        # every import binding the name, by the language's own rule, resolved to no file
    # For an unresolved name, the module paths it may still come from inside the tree: those of a
    # statement whose verdict could not place it (a package root or sys.path entry reveal does not
    # model, as a monorepo's python_modules/dagster). Empty: every statement is outside the tree.
    modules: Tuple[ModulePath, ...] = ()
    # The module path the name is imported from, as the import spells it ('os.path.join' for
    # ``from os.path import join``), when every statement binding it agrees; None otherwise.
    origin: Optional[str] = None

def _module_paths(stmt: ImportStatement) -> Tuple[ModulePath, ...]:
    """Where ``stmt``'s module, and a named import's member as a submodule, would sit under some
    root: ``from a.b import c`` -> ('a', 'b') and ('a', 'b', 'c'). None for an import the
    extractor places outside the tree, or a relative one (resolution had its directory)."""
    if stmt.intra_verdict is False or stmt.is_relative:
        return ()
    module = tuple(part for part in _SEPARATORS.split(stmt.module_name or '') if part)
    if not module:
        return ()
    members = [entry.split(' as ')[0].strip() for entry in stmt.imported_names if entry != '*']
    return (module, *((*module, member) for member in members if member))


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
    (and without a package's ``__init__``/``index``/``mod``) ends with the module's parts."""
    parts = tuple(PurePosixPath(file_path.replace('\\', '/')).with_suffix('').parts)
    forms = [parts, parts[:-1]] if parts and parts[-1] in _PACKAGE_FILES else [parts]
    return any(len(form) >= len(module) and form[-len(module):] == module
               for module in modules for form in forms)


def file_bindings(imports: Iterable[ImportStatement]) -> Dict[str, Binding]:
    """Local name -> binding, from one file's resolved import statements. A name names a file only
    when every statement that binds it names the same one, and is unresolved only when none of them
    resolved; a bare import whose bound name is a guess (``binds_reliably``: C ``#include <array>``
    binds no ``array``) is never unresolved. Such an import still names its file when it resolved
    in-tree (Zig ``const config = @import("config.zig")``), which only ever narrows candidates."""
    bindings: Dict[str, Binding] = {}
    for stmt in imports:
        target = str(stmt.resolved_path) if stmt.resolved_path else None
        unresolved = target is None and binds_reliably(stmt)
        modules = _module_paths(stmt) if unresolved else ()
        origins = _origins(stmt)
        for name in bound_names(stmt):
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


def _absolute(path: Union[str, Path]) -> str:
    return os.path.normcase(os.path.abspath(path))
