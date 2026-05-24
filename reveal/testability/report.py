"""Join patch pressure and boundary profiles into a testability report."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .boundaries import BoundaryProfile, collect_boundary_profiles, module_name_from_file, profile_score
from .patches import PatchGroup, group_patches, scan_patches


def build_testability_report(
    src_path: str,
    test_paths: Sequence[str],
    top: int = 20,
    min_patches: int = 3,
    min_categories: int = 3,
    include_unresolved: bool = False,
) -> Dict[str, Any]:
    """Build the composed testability pressure report."""
    patches = scan_patches(test_paths)
    patch_groups = group_patches(patches, group_by='target', limit=0, min_count=min_patches)
    profiles = collect_boundary_profiles(src_path)

    profile_rows = _rank_profiles(src_path, profiles, patch_groups, min_categories)
    target_rows = _rank_targets(src_path, patch_groups, profiles, include_unresolved)

    target_rows = target_rows[:top] if top > 0 else target_rows
    profile_rows = profile_rows[:top] if top > 0 else profile_rows

    return {
        'contract_version': '1.1',
        'type': 'testability_report',
        'source': str(Path(src_path)),
        'source_type': 'directory' if Path(src_path).is_dir() else 'file',
        'tests': [str(Path(p)) for p in test_paths],
        'summary': {
            'total_patch_uses': len(patches),
            'total_patch_targets': len({p.target_qualname or p.target_raw for p in patches}),
            'patch_groups_reported': len(target_rows),
            'boundary_profiles_reported': len(profile_rows),
        },
        'patch_hotspots': target_rows,
        'boundary_hotspots': profile_rows,
        'meta': {
            'parse_mode': 'python_ast',
            'confidence': 0.75,
            'warnings': [
                {'code': 'W-TESTABILITY-1', 'message': 'Static target resolution is best-effort.'},
                {'code': 'W-TESTABILITY-2', 'message': 'Patch pressure is advisory; mocking external boundaries can be correct.'},
            ],
            'errors': [],
        },
    }


def _rank_targets(
    src_path: str,
    patch_groups: List[PatchGroup],
    profiles: List[BoundaryProfile],
    include_unresolved: bool,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for group in patch_groups:
        matches = _matching_profiles(src_path, group.key, profiles)
        if not matches and not include_unresolved:
            # Keep highly repeated unresolved targets; they are still useful.
            if group.patch_count < 10:
                continue
        categories = sorted({cat for prof in matches for cat in prof.categories})
        rows.append({
            **group.to_dict(),
            'related_profiles': [
                {
                    'file': p.file,
                    'function': p.function,
                    'line': p.line,
                    'complexity': p.complexity,
                    'lines': p.lines,
                    'categories': sorted(p.categories),
                }
                for p in matches[:5]
            ],
            'boundary_categories': categories,
            'suggestion': _suggestion(group.key, categories, group.patch_count),
        })
    rows.sort(key=lambda r: (len(r['boundary_categories']), r['score'], r['patch_count']), reverse=True)
    return rows


def _rank_profiles(
    src_path: str,
    profiles: List[BoundaryProfile],
    patch_groups: List[PatchGroup],
    min_categories: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for profile in profiles:
        related_patch_count = _related_patch_count(src_path, profile, patch_groups)
        category_count = len(profile.categories)
        if category_count < min_categories and not (related_patch_count and category_count >= 2):
            continue
        score = profile_score(profile, related_patch_count)
        rows.append({
            **profile.to_dict(),
            'patch_count': related_patch_count,
            'score': score,
            'suggestion': _profile_suggestion(profile, related_patch_count),
        })
    rows.sort(key=lambda r: (r['score'], len(r['categories']), r['complexity']), reverse=True)
    return rows


def _matching_profiles(src_path: str, target: str, profiles: List[BoundaryProfile]) -> List[BoundaryProfile]:
    matches = []
    for profile in profiles:
        if _target_matches_profile(src_path, target, profile):
            matches.append(profile)
    symbol = _target_symbol(target)
    matches.sort(key=lambda p: (p.function != symbol, -len(p.categories), -p.complexity))
    return matches


def _related_patch_count(src_path: str, profile: BoundaryProfile, patch_groups: List[PatchGroup]) -> int:
    total = 0
    for group in patch_groups:
        if _target_matches_profile(src_path, group.key, profile):
            total += group.patch_count
    return total


def _target_matches_profile(src_path: str, target: str, profile: BoundaryProfile) -> bool:
    symbol = _target_symbol(target)
    module = _target_module(target)
    module_name = module_name_from_file(profile.file, src_path)

    if profile.function != symbol:
        return False
    if not module:
        return True
    if _is_generic_patch_object_module(module):
        return True
    return _module_matches(module, module_name)


@lru_cache(maxsize=None)
def _target_symbol(target: str) -> str:
    parts = target.split('.')
    return parts[-1] if parts else target


@lru_cache(maxsize=None)
def _target_module(target: str) -> str:
    parts = target.split('.')
    return '.'.join(parts[:-1])


def _is_generic_patch_object_module(module: str) -> bool:
    return module in {'adapter', 'obj', 'target', 'module', 'mock'}


@lru_cache(maxsize=None)
def _module_matches(target_module: str, source_module: str) -> bool:
    if not target_module or not source_module:
        return False
    target_parts = target_module.split('.')
    source_parts = source_module.split('.')
    for i in range(0, len(target_parts) - len(source_parts) + 1):
        if target_parts[i:i + len(source_parts)] == source_parts:
            return True
    return target_module.endswith(source_module) or source_module.endswith(target_module)


def _suggestion(target: str, categories: List[str], patch_count: int) -> str:
    if 'network_client' in categories or 'filesystem' in categories:
        return 'Boundary mocking may be normal; consider a fake collaborator if setup repeats.'
    if patch_count >= 10:
        return 'Repeated patching may indicate a useful seam for extracting runtime wiring from decision logic.'
    if target.split('.')[-1].startswith('_'):
        return 'Private target patching can indicate tests are reaching past a stable boundary.'
    return 'Review whether the patched dependency has a clearer boundary.'


def _profile_suggestion(profile: BoundaryProfile, patch_count: int) -> str:
    if patch_count:
        return 'Patch pressure overlaps with boundary fan-out; consider separating pure decisions from runtime effects.'
    if len(profile.categories) >= 4:
        return 'Function crosses several runtime boundaries; review before risky changes.'
    return 'Boundary fan-out is advisory; inspect if tests or changes cluster here.'
