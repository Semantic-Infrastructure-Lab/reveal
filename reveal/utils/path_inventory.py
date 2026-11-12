"""Measured named-path inspection shared by installation diagnostic readers."""
import stat as stat_module
from pathlib import Path
from typing import Any, Dict

from .path_utils import failure_of


def path_info(p: Path) -> Dict[str, Any]:
    try:
        metadata = p.stat()
    except (FileNotFoundError, NotADirectoryError):
        return {'path': str(p), 'exists': False}
    except OSError as exc:
        return {'path': str(p), 'exists': None, 'error_phase': 'metadata', 'cause': type(exc).__name__,
                'error': f'metadata unreadable: {failure_of(exc).cause}'}
    if stat_module.S_ISDIR(metadata.st_mode):
        count = 0
        try:
            for _ in p.iterdir():
                count += 1
        except OSError as exc:
            return {'path': str(p), 'exists': True, 'kind': 'dir', 'count': None,
                    'entries_seen': count, 'error_phase': 'directory-count', 'cause': type(exc).__name__,
                    'error': f'directory unreadable: {failure_of(exc).cause}'}
        return {'path': str(p), 'exists': True, 'kind': 'dir', 'count': count}
    return {'path': str(p), 'exists': True, 'kind': 'file', 'size_bytes': metadata.st_size}



def valid_path_info(row):
    if not isinstance(row, dict) or not isinstance(row.get('path'), str):
        return False
    exists = row.get('exists')
    if row.get('error'):
        if 'entries_seen' in row and (type(row['entries_seen']) is not int or row['entries_seen'] < 0):
            return False
        return exists is None or exists is True
    if type(exists) is not bool:
        return False
    if not exists:
        return True
    key = 'count' if row.get('kind') == 'dir' else 'size_bytes'
    return type(row.get(key)) is int and row[key] >= 0



def path_counts(paths):
    failed = sum(bool(row.get('error')) for row in paths.values())
    return {'candidate_paths': len(paths), 'analyzed_paths': len(paths) - failed,
            'failed_paths': failed,
            'usable_paths': sum(type(row.get('exists')) is bool for row in paths.values())}
