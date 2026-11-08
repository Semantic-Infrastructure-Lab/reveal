"""Maven build modules as package units (BACK-2552, the Java consumer of BACK-2559's package model).

A Maven reactor builds each module against its own sources and the modules it depends on, and a
dependency names a module by coordinate (``groupId:artifactId:version``), never by path. Guava keeps two
reactors in one repository (``pom.xml`` and ``android/pom.xml``) whose modules share groupId and
artifactId and differ only in version (``...-jre`` vs ``...-android``), so the same fully qualified type
exists twice and only the coordinate says which copy an importer compiles against.

Each pom.xml becomes one unit named by its coordinate. As in Maven, groupId and version come from the
``<parent>`` block when the pom does not state them, and ``${...}`` values are filled from the pom's own
``<properties>``, then its parent's (the pom at ``<relativePath>``, default ``../pom.xml``, when it was
read and is the parent the block names), then ``project.version``/``project.parent.version``/
``project.groupId``. A dependency links to the in-tree unit with exactly its coordinate. Anything the poms
read do not say stays unknown and links nothing: a version Maven would take from a
``<dependencyManagement>`` section or a pom that was not read, a value built from several properties.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Dict, Iterator, List, NamedTuple, Optional, Tuple

from .packages import PackageUnit

_NAMESPACE = re.compile(r'^\{[^}]*\}')
_PROPERTY = re.compile(r'^\$\{([^}]+)\}$')
_MAX_PARENTS = 16  # a parent chain is a handful of poms; a cycle stops here


class _RawPom(NamedTuple):
    manifest: Path
    group: Optional[str]
    artifact: Optional[str]
    version: Optional[str]
    parent: Optional[Tuple[Optional[str], Optional[str], Optional[str], Path]]  # group, artifact, version, pom path
    properties: Dict[str, Optional[str]]
    dependencies: Tuple[Tuple[Optional[str], Optional[str], Optional[str]], ...]


class _Pom(NamedTuple):
    manifest: Path
    group: str
    artifact: str
    version: Optional[str]
    dependencies: Tuple[Tuple[Optional[str], Optional[str], Optional[str]], ...]


def _local(tag: str) -> str:
    return _NAMESPACE.sub('', tag) if isinstance(tag, str) else ''


def _child(element: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    if element is None:
        return None
    return next((child for child in element if _local(child.tag) == name), None)


def _children(element: Optional[ET.Element], name: str) -> List[ET.Element]:
    """The children of ``element``'s child ``name`` (an Element's truth value is its child count, so never
    ``child or []``)."""
    child = _child(element, name)
    return list(child) if child is not None else []


def _text(element: Optional[ET.Element], name: str) -> Optional[str]:
    child = _child(element, name)
    text = (child.text or '').strip() if child is not None else ''
    return text or None


def _read_pom(manifest: Path, on_error: Callable[[OSError], None]) -> Optional[_RawPom]:
    """One pom as written; None when it cannot be read (reported) or is not XML (Maven rejects it too)."""
    try:
        with open(manifest, 'rb') as f:
            root = ET.parse(f).getroot()
    except OSError as error:
        on_error(error)
        return None
    except ET.ParseError:
        return None
    block = _child(root, 'parent')
    parent = None
    if block is not None:
        relative = _text(block, 'relativePath') or '../pom.xml'
        location = (manifest.parent / relative).resolve()
        if location.is_dir() or not relative.endswith('.xml'):
            location = location / 'pom.xml'
        parent = (_text(block, 'groupId'), _text(block, 'artifactId'), _text(block, 'version'), location)
    return _RawPom(
        manifest, _text(root, 'groupId'), _text(root, 'artifactId'), _text(root, 'version'), parent,
        {_local(p.tag): (p.text or '').strip() or None for p in _children(root, 'properties')},
        tuple((_text(dep, 'groupId'), _text(dep, 'artifactId'), _text(dep, 'version'))
              for dep in _children(root, 'dependencies') if _local(dep.tag) == 'dependency'))


def _parent_of(raw: _RawPom, read: Dict[Path, _RawPom]) -> Optional[_RawPom]:
    """The pom ``raw``'s parent block names, when it was read at the block's path and is that parent."""
    if raw.parent is None:
        return None
    group, artifact, _version, location = raw.parent
    candidate = read.get(location)
    if candidate is None or candidate.artifact != artifact:
        return None
    return candidate if (candidate.group or (candidate.parent or (None,))[0]) == group else None


def _properties(raw: _RawPom, read: Dict[Path, _RawPom]) -> Dict[str, Optional[str]]:
    """``raw``'s properties over its ancestors' (the nearest definition wins)."""
    chain: List[_RawPom] = []
    current: Optional[_RawPom] = raw
    while current is not None and len(chain) < _MAX_PARENTS and current not in chain:
        chain.append(current)
        current = _parent_of(current, read)
    merged: Dict[str, Optional[str]] = {}
    for pom in reversed(chain):
        merged.update(pom.properties)
    return merged


def _interpolate(value: Optional[str], known: Dict[str, Optional[str]]) -> Optional[str]:
    """A literal, or a whole-value ``${name}`` Maven fills from ``known``; None when it cannot be told."""
    if value is None:
        return None
    match = _PROPERTY.match(value)
    if match is None:
        return None if '${' in value else value
    return known.get(match.group(1))


def _resolve(raw: _RawPom, read: Dict[Path, _RawPom]) -> Optional[_Pom]:
    """``raw`` with its coordinate and dependency versions filled; None without a groupId and artifactId."""
    parent_group, _artifact, parent_version, _location = raw.parent or (None, None, None, None)
    known = _properties(raw, read)
    group = _interpolate(raw.group, known) if raw.group else parent_group
    known.update({'project.parent.version': parent_version, 'project.groupId': group})
    version = _interpolate(raw.version or parent_version, known)
    known.update({'project.version': version, 'version': version, 'pom.version': version})
    if not group or not raw.artifact:
        return None
    return _Pom(raw.manifest, group, raw.artifact, version,
                tuple((_interpolate(g, known), a, _interpolate(v, known)) for g, a, v in raw.dependencies))


def _coordinate(pom: _Pom) -> str:
    return f'{pom.group}:{pom.artifact}:{pom.version or "?"}'


def _links(pom: _Pom, by_coordinate: Dict[Tuple[str, str, str], List[_Pom]]) -> Iterator[Tuple[str, Path]]:
    for group, artifact, version in pom.dependencies:
        if group is None or artifact is None or version is None:
            continue  # the poms read do not say which module; never guess (rule 12)
        same = by_coordinate.get((group, artifact, version), [])
        if len(same) == 1 and same[0].manifest != pom.manifest:
            yield _coordinate(same[0]), same[0].manifest


def maven_units(manifests: List[Path], on_error: Callable[[OSError], None]) -> List[PackageUnit]:
    """Each pom.xml read: its coordinate as the unit's name and the in-tree modules it depends on."""
    read = {raw.manifest.resolve(): raw for m in manifests if (raw := _read_pom(m, on_error)) is not None}
    poms = [pom for raw in read.values() if (pom := _resolve(raw, read)) is not None]
    by_coordinate: Dict[Tuple[str, str, str], List[_Pom]] = {}
    for pom in poms:
        if pom.version is not None:
            by_coordinate.setdefault((pom.group, pom.artifact, pom.version), []).append(pom)
    return [PackageUnit(pom.manifest, _coordinate(pom),
                        local_dependencies=tuple(sorted(set(_links(pom, by_coordinate))))) for pom in poms]
