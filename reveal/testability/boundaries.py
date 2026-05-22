"""Conservative boundary fan-out profiling for Python code."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Set


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


_CATEGORY_PATTERNS = {
    'network_client': (
        'requests.', 'httpx.', 'aiohttp.', 'urllib.', 'socket.', 'dns.',
        'check_ssl', 'probe_http', 'resolve',
    ),
    'persistence': (
        'sqlite3', 'sqlalchemy', 'redis', 'cursor.', 'conn.execute',
        'connection.execute', 'save_', 'load_', 'write_state', 'record_',
    ),
    'filesystem': (
        'open', 'Path(', 'Path.', '.read_text', '.write_text', '.write_bytes',
        'os.path', 'os.makedirs', 'shutil.',
    ),
    'notification': (
        'discord', 'slack', 'email', 'webhook', 'notify', 'alert', 'send_',
    ),
    'event_telemetry': (
        'logger.', 'logging.', 'metrics', 'emit', 'event', 'audit',
    ),
    'clock_sleep': (
        'time.time', 'time.sleep', 'datetime.now', 'datetime.utcnow',
        'asyncio.sleep', '.today',
    ),
    'env_config': (
        'os.environ', 'os.getenv', 'getenv', 'RevealConfig.get', 'get_config',
    ),
    'process_global': (
        'sys.exit', 'os._exit', 'global', 'singleton', 'registry',
    ),
}

_MUTATION_TAILS = {'append', 'extend', 'update', 'setdefault', 'pop', 'remove', 'clear', 'add'}


def collect_boundary_profiles(path: str) -> List[BoundaryProfile]:
    """Collect conservative boundary profiles for functions under path."""
    from reveal.adapters.ast.analysis import collect_structures

    structures = collect_structures(path)
    profiles: List[BoundaryProfile] = []
    imports_by_file = _imports_by_file(structures)

    for file_struct in structures:
        file_path = file_struct.get('file', '')
        imports = imports_by_file.get(file_path, [])
        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            calls = [str(c) for c in elem.get('calls', [])]
            categories = _classify_categories(calls, imports)
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


def _classify_categories(calls: List[str], imports: List[str]) -> Set[str]:
    text_items = [c.lower() for c in calls] + [i.lower() for i in imports]
    categories: Set[str] = set()
    for category, patterns in _CATEGORY_PATTERNS.items():
        for item in text_items:
            if any(pattern.lower() in item for pattern in patterns):
                categories.add(category)
                break
    return categories


def _mutation_sites(calls: List[str], base_line: int) -> List[int]:
    sites: List[int] = []
    for idx, call in enumerate(calls):
        tail = call.split('.')[-1].split('(')[0]
        if tail in _MUTATION_TAILS:
            sites.append(base_line + idx)
    return sites


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
    return '.'.join(p for p in parts if p != '__init__')
