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
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class PackageUnit:
    """One package a manifest declares, as its language's importers see it."""
    manifest: Path                       # the manifest file, resolved
    name: str                            # how importers spell the package (Cargo: the library crate name)
    library_root: Optional[Path] = None  # the root module file that name resolves to; None: no library
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


EMPTY_PACKAGES = PackageModel()
