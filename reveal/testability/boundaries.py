"""Conservative boundary fan-out profiling, per function, for every analyzed language.

A function's boundary categories come from its OWN calls, classified by the same
per-language taxonomy `--sideeffects` uses (`nav_effects.classify_call`), so the two
cannot disagree. BACK-1402: the old classifier substring-matched a Python/reveal-internal
vocabulary ('open', 'event', 'global', 'resolve', `RevealConfig.get`) against the calls
plus the whole file's import list -- every function in a file got the same labels, and a
pure Java string builder was "network_client, filesystem, process_global" while
`--sideeffects` said it had none.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class BoundaryProfile:
    """Runtime-boundary profile for one function or method."""

    file: str
    function: str
    line: int
    lines: int
    complexity: int
    categories: Set[str]
    calls: List[str]
    imports: List[str]
    mutation_sites: List[int]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['categories'] = sorted(self.categories)
        return data


# nav_effects kind -> testability category. `cache`/`session` are stateful stores, so
# they count as persistence; kinds not listed here are not a test boundary.
_EFFECT_CATEGORY = {
    'http': 'network_client',
    'db': 'persistence',
    'cache': 'persistence',
    'session': 'persistence',
    'file': 'filesystem',
    'log': 'event_telemetry',
    'sleep': 'clock_sleep',
    'env': 'env_config',
    'hard_stop': 'process_global',
}

_MUTATION_TAILS = {'append', 'extend', 'update', 'setdefault', 'pop', 'remove', 'clear', 'add'}


def collect_boundary_profiles(path: str) -> List[BoundaryProfile]:
    """Collect conservative boundary profiles for functions under path."""
    from reveal.adapters.ast.analysis import collect_structures

    from reveal.registry import language_for_extension

    structures = collect_structures(path)
    profiles: List[BoundaryProfile] = []
    imports_by_file = _imports_by_file(structures)

    for file_struct in structures:
        file_path = file_struct.get('file', '')
        imports = imports_by_file.get(file_path, [])
        language = language_for_extension(Path(file_path).suffix.lower())
        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            calls = [str(c) for c in elem.get('calls', [])]
            categories = _classify_categories(calls, language)
            mutation_sites = _mutation_sites(calls, elem.get('line', 0))
            if mutation_sites:
                categories.add('mutation')
            profiles.append(BoundaryProfile(
                file=file_path,
                function=elem.get('name', ''),
                line=int(elem.get('line', 0) or 0),
                lines=int(elem.get('line_count', 0) or 0),
                complexity=int(elem.get('complexity', 0) or 0),
                categories=categories,
                calls=calls,
                imports=imports,
                mutation_sites=mutation_sites,
                confidence=0.75 if categories else 0.6,
            ))
    return profiles


def profile_score(profile: BoundaryProfile, patch_count: int = 0) -> float:
    """Return a simple explainable boundary pressure score."""
    score = len(profile.categories) * 3
    if profile.complexity > 10:
        score += min(10, profile.complexity - 10)
    if profile.lines > 80:
        score += 4
    elif profile.lines > 50:
        score += 2
    if profile.mutation_sites:
        score += 2
    if patch_count:
        score += min(10, patch_count / 2)
    return score


def _imports_by_file(structures: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for file_struct in structures:
        file_path = file_struct.get('file', '')
        imports = []
        for elem in file_struct.get('elements', []):
            if elem.get('category') == 'imports' and elem.get('name'):
                imports.append(str(elem.get('name')))
        result[file_path] = imports
    return result


def _classify_categories(calls: List[str], language: Optional[str]) -> Set[str]:
    """Boundary categories of one function's own calls (never its file's imports)."""
    from reveal.adapters.ast.nav_effects import classify_call

    categories: Set[str] = set()
    for call in calls:
        category = _EFFECT_CATEGORY.get(classify_call(call, language) or '')
        if category:
            categories.add(category)
    return categories


def _mutation_sites(calls: List[str], base_line: int) -> List[int]:
    sites: List[int] = []
    for idx, call in enumerate(calls):
        tail = call.split('.')[-1].split('(')[0]
        if tail in _MUTATION_TAILS:
            sites.append(base_line + idx)
    return sites


@lru_cache(maxsize=None)
def module_name_from_file(file_path: str, src_root: str) -> str:
    """Best-effort module name for a file under a source root."""
    try:
        rel = Path(file_path).resolve().relative_to(Path(src_root).resolve())
    except ValueError:
        rel = Path(file_path).name
    if isinstance(rel, Path):
        parts = list(rel.with_suffix('').parts)
    else:
        parts = [str(rel)]
    name_parts = [p for p in parts if p != '__init__']
    if not name_parts:
        # file_path IS src_root's own __init__.py — its module identity is the
        # scanned package itself, not "no module" (which would make it match
        # any symbol-name-only target regardless of qualifier).
        return Path(src_root).resolve().name
    return '.'.join(name_parts)
