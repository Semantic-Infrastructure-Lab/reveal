"""The per-scan package model (BACK-2559): which package each source file belongs to, where that package's
target roots are, and which in-tree package an import name spells.

Built once per scan in the resolution's index phase (``ProjectResolver.prepare``) from the manifests the
scanned files' languages declare (``LanguageExtractor.package_markers``), and read by resolution. One owner
for manifest facts: a language reads its manifests here instead of again in each method that needs them.
Plain data, so it travels to pool workers with the other resolution inputs. Anything a manifest does not
say stays unknown (None), never a guess.
"""
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Dict, FrozenSet, List, NamedTuple, Optional, Set, Tuple


@dataclass(frozen=True)
class PackageUnit:
    """One package a manifest declares, as its language's importers see it."""
    manifest: Path                       # the manifest file, resolved (Python: the top package's __init__.py)
    name: str                            # how importers spell the package (Cargo: the library crate name; Go: the module path)
    library_root: Optional[Path] = None  # what that name resolves to (Cargo: the root module file; Go: the module
                                         # directory, a package being a directory); None: no library
    # Every target's root-module directory (Cargo: lib, bins, tests, examples, benches, build script):
    # a path from the root of the target a file belongs to starts at the deepest one holding the file.
    target_roots: Tuple[Path, ...] = ()
    # (name as importers spell it, the depended-on package's manifest, resolved): in-tree dependencies only.
    local_dependencies: Tuple[Tuple[str, Path], ...] = ()


@dataclass(frozen=True)
class PackageModel:
    """Every package unit of one scan, and every manifest directory read (a manifest that declares no unit,
    such as a virtual workspace or an unreadable one, still ends the climb to a file's package)."""
    units: Tuple[PackageUnit, ...] = ()
    manifest_dirs: Tuple[Path, ...] = ()

    @cached_property
    def _unit_at(self) -> Dict[Path, Optional[PackageUnit]]:
        at: Dict[Path, Optional[PackageUnit]] = {d: None for d in self.manifest_dirs}
        at.update({unit.manifest.parent: unit for unit in self.units})
        return at

    @cached_property
    def _by_manifest(self) -> Dict[Path, PackageUnit]:
        return {unit.manifest: unit for unit in self.units}

    def owns(self, directory: Path) -> bool:
        """Whether the model read the manifest nearest ``directory`` (a resolved directory). False means it
        knows nothing about ``directory``: the caller's own convention applies there, not an absence."""
        return any(d in self._unit_at for d in (directory, *directory.parents))

    def unit_for(self, directory: Path) -> Optional[PackageUnit]:
        """The unit of the manifest nearest ``directory`` (a resolved directory); None when that manifest
        declares none or no manifest was read."""
        for candidate in (directory, *directory.parents):
            if candidate in self._unit_at:
                return self._unit_at[candidate]
        return None

    def target_root_for(self, file: Path) -> Optional[Path]:
        """The root-module directory of the target ``file`` (resolved) belongs to: the deepest target root of
        its package that holds it. None: its package declares no target holding it."""
        unit = self.unit_for(file.parent)
        holding = [root for root in (unit.target_roots if unit else ()) if root == file.parent or root in file.parents]
        return max(holding, key=lambda root: len(root.parts)) if holding else None

    def named_unit(self, directory: Path, name: str) -> Optional[PackageUnit]:
        """The in-tree unit ``name`` spells for a file in ``directory`` (resolved): one of its package's local
        dependencies, or its own library (an integration test, a binary). None: not an in-tree package."""
        unit = self.unit_for(directory)
        if unit is None:
            return None
        for spelled, manifest in unit.local_dependencies:
            if spelled == name:
                return self._by_manifest.get(manifest)
        return unit if name == unit.name and unit.library_root is not None else None

    def build_layers(self, directory: Path) -> Tuple[FrozenSet[Path], ...]:
        """The manifests a file in ``directory`` (resolved) compiles against, nearest first: its own unit,
        then every in-tree unit reachable through local dependencies. A build-module language (Maven) breaks
        a tie between same-named declarations with them (BACK-2552). Empty: its package declares no unit."""
        unit = self.unit_for(directory)
        if unit is None:
            return ()
        seen = {unit.manifest}
        frontier = [manifest for _name, manifest in unit.local_dependencies]
        reachable: Set[Path] = set()
        while frontier:
            manifest = frontier.pop()
            if manifest in seen:
                continue
            seen.add(manifest)
            reachable.add(manifest)
            dependency = self._by_manifest.get(manifest)
            if dependency is not None:
                frontier.extend(m for _name, m in dependency.local_dependencies)
        return (frozenset({unit.manifest}), frozenset(reachable))

    def manifest_of(self, file: Path) -> Optional[Path]:
        """The manifest of the unit ``file`` (resolved) belongs to; None outside every unit."""
        unit = self.unit_for(file.parent)
        return unit.manifest if unit is not None else None

    def local_units(self, directory: Path) -> Tuple[Tuple[str, PackageUnit], ...]:
        """(name as importers spell it, unit) for every in-tree unit a file in ``directory`` (resolved) can name: its
        own package first, then each local dependency the model read (Go matches an import path against all of
        them, longest first). Empty: no manifest of ``directory``'s package declares a unit."""
        unit = self.unit_for(directory)
        if unit is None:
            return ()
        return ((unit.name, unit),) + tuple((spelled, dep) for spelled, manifest in unit.local_dependencies
                                            if (dep := self._by_manifest.get(manifest)) is not None)


EMPTY_PACKAGES = PackageModel()


class BuildScope(NamedTuple):
    """What one importer compiles against (BACK-2552): the scan's model and the importer's
    :meth:`PackageModel.build_layers`. Breaks a tie between files declaring one qualified name."""
    model: PackageModel
    layers: Tuple[FrozenSet[Path], ...]

    def pick(self, matches: List[Path]) -> Optional[Path]:
        """The one match in the nearest layer that holds any; None when that layer holds several (still
        ambiguous) or no layer holds one (the name is declared only outside what the importer builds with)."""
        for layer in self.layers:
            inside = [m for m in matches if self.model.manifest_of(m.resolve()) in layer]
            if len(inside) == 1:
                return inside[0]
            if inside:
                return None
        return None
