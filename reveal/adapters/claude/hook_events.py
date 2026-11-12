"""Hook-event source acquisition, separate from the root event catalog."""
import stat
from copy import deepcopy
from typing import Any, Dict

from ...utils.results import note_warning
from .workspace_scan import WorkspaceScan, _proof_error

_ENTRY_ERRORS = (OSError, ValueError, OverflowError)


def read_hook_event(hooks_dir, event_name, base, skipped_warning, timestamp) -> Dict[str, Any]:
    scan = WorkspaceScan(legacy_discovery_error=True)
    result = {**base, 'event': event_name}
    if not scan.directory(hooks_dir, required=True):
        result.update(hooks=[], total=0,
                      error=f'Hooks directory not found: {hooks_dir}' if scan.request_rejected else scan.root_error)
        return _attach(scan, result)
    path = hooks_dir / event_name
    try:
        selected = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        scan.request_rejected = True
        result['error'] = f'Hook event not found: {event_name}'
        return _attach(scan, result)
    except OSError as exc:
        scan.discovery_errors.append((path, exc))
        result['error'] = str(exc)
        return _attach(scan, result)
    kind = 'file' if stat.S_ISREG(selected.st_mode) else 'directory'
    result.update(source=str(path), source_type=kind, kind=kind)
    if kind == 'file':
        result['path'] = str(path)
        _read_file(scan, path, result, timestamp)
    else:
        _read_directory(scan, path, result, timestamp)
        note_warning(result, skipped_warning('hook scripts', scan.entry_errors))
    return _attach(scan, result)


def _read_file(scan, path, result, timestamp):
    scan.candidates.add(str(path))
    try:
        result['content'] = scan.read_text(path)
        scan.complete(path)
        result.update(_metadata(path, timestamp))
    except _ENTRY_ERRORS as exc:
        scan.entry_errors.append((path, exc))
        result['error'] = str(exc)


def _read_directory(scan, path, result, timestamp):
    scripts = []
    entries = sorted(scan.entries(path, legacy_error=True))
    scan.candidates.update(str(p) for p in entries)
    for script in entries:
        try:
            scripts.append({'name': script.name, 'path': str(script), **_metadata(script, timestamp)})
            scan.complete(script)
        except _ENTRY_ERRORS as exc:
            scan.entry_errors.append((script, exc))
    result['scripts'] = scripts


def _metadata(path, timestamp):
    metadata = path.stat()
    return {'size_bytes': metadata.st_size, 'executable': bool(metadata.st_mode & 0o111),
            'modified': timestamp(metadata.st_mtime).isoformat(timespec='seconds')}


def _attach(scan, result: Dict[str, Any]) -> Dict[str, Any]:
    result = scan.attach(result)
    result['meta']['workspace_analysis']['hook_event'] = {
        'kind': result.get('kind', 'unresolved'), 'source': result['source'],
    }
    return result


def hook_event_requirement_error(adapter, result, prior_facts):
    proof = result.get('meta', {}).get('workspace_analysis')
    error = _proof_error(proof)
    if error:
        return error
    if prior_facts is None:
        adapter._hook_event_proof = deepcopy(proof)
    if proof != adapter._hook_event_proof:
        return 'Claude presentation cannot change hook-event acquisition decisions'
    event = proof.get('hook_event', {})
    kind = event.get('kind')
    if result.get('source') != event.get('source'):
        return 'Claude hook-event answer changed selected source identity'
    if kind == 'unresolved':
        return None
    if kind not in ('file', 'directory') or result.get('kind') != kind or result.get('source_type') != kind:
        return 'Claude hook-event answer missing consistent selected kind'
    if kind == 'directory' and not isinstance(result.get('scripts'), list):
        return 'Claude hook-event answer missing script observations'
    if kind == 'file' and proof['analyzed_entries'] and not isinstance(result.get('content'), str):
        return 'Claude hook-event answer missing observed content'
    return None


def hook_event_fields(result):
    if result.get('kind') == 'directory':
        return {'scripts': list}
    return {'content': str} if 'content' in result else {}
