"""Built-in rule profiles for reveal check --profile NAME."""

from typing import Dict, List, Optional

# Each profile specifies select and/or ignore lists.
# select: list of rule codes/prefixes to enable (same syntax as --select)
# ignore: list of rule codes/prefixes to suppress (same syntax as --ignore)
BUILTIN_PROFILES: Dict[str, Dict] = {
    'maintenance': {
        'description': 'Routine doc and link health — broken links, missing front matter, oversized files',
        'select': ['L001', 'F001', 'M101'],
        'ignore': [],
    },
    'security': {
        'description': 'Security-sensitive rules — hardcoded secrets, infrastructure misconfigs',
        'select': ['S', 'N'],
        'ignore': [],
    },
    'ci-strict': {
        'description': 'All stable rules — bugs, complexity, imports, maintainability, security, types',
        'select': ['B', 'C', 'I', 'M', 'S', 'T'],
        'ignore': [],
    },
    'recommended': {
        'description': (
            'Rules with confirmed cross-language correctness (BACK-432) — the safe '
            'starting point for a first check on a non-Python repo, unlike the full '
            'rule set which includes rules only ever verified against Python'
        ),
        'select': [
            'I001', 'I002', 'I005',  # import health: unused/circular/duplicate
            'C901', 'C902', 'C905',  # complexity/length/nesting
            'D001', 'M501',          # duplicate functions, unresolved comment markers
            'S001',                  # hardcoded secrets
            'E501', 'U501', 'M101',  # line length, insecure URL, file size
        ],
        'ignore': [],
    },
}


def resolve_profile(
    name: str,
    user_profiles: Optional[Dict[str, Dict]] = None,
) -> Dict[str, List[str]]:
    """Return {'select': [...], 'ignore': [...]} for the named profile.

    Raises KeyError if the profile is not found.
    """
    profiles = dict(BUILTIN_PROFILES)
    if user_profiles:
        profiles.update(user_profiles)
    if name not in profiles:
        available = ', '.join(sorted(profiles.keys()))
        raise KeyError(f"Unknown profile '{name}'. Available: {available}")
    entry = profiles[name]
    return {
        'select': list(entry.get('select', [])),
        'ignore': list(entry.get('ignore', [])),
    }


def list_profiles(user_profiles: Optional[Dict[str, Dict]] = None) -> List[Dict]:
    """Return all profiles (built-in + user-defined) as a list of dicts."""
    profiles = dict(BUILTIN_PROFILES)
    if user_profiles:
        profiles.update(user_profiles)
    result = []
    for name, entry in sorted(profiles.items()):
        result.append({
            'name': name,
            'description': entry.get('description', ''),
            'select': entry.get('select', []),
            'ignore': entry.get('ignore', []),
            'builtin': name in BUILTIN_PROFILES,
        })
    return result
