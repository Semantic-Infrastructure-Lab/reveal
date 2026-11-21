"""Codex workspace lists: memories, rules, skills and plugins, with measured acquisition (BACK-2618 Step 3).

Each reader lists its directory under the Codex home through the shared workspace-list receipt
(``utils.workspace_scan``, ``meta.workspace_analysis``), as Claude's agents, plans, memory and hooks do (BACK-946
parity). The directory's confirmed absence is a complete empty answer, ``source_absent`` in the receipt (ruling Q7,
the goals precedent); an unreadable directory, entry or manifest is lost input, exit 3, with the readable entries
kept and the failure named by its cause; a named skill or plugin that matches nothing is an invalid request, exit 2,
only when every definition was read (otherwise its absence is not confirmed, exit 3).
"""
import json
import stat
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from reveal.reveal_types import CONTRACT_VERSION
from reveal.utils.lines import split_lines
from reveal.utils.path_utils import to_posix

from ....errors import MissingResourceError
from ....utils.results import ResultBuilder
from ....utils.workspace_scan import WorkspaceScan, workspace_execution_facts, workspace_list_error

WORKSPACE_RULE = ('Files the reader selects under its Codex directory, in path order, before display cuts; analyzed '
                  'plus failed equals candidates; an unreadable directory counts as a discovery failure')
_ENTRY_ERRORS = (OSError, ValueError)  # a read, a stat, invalid JSON (a ValueError) or a manifest that is no object
LIST_FIELDS = {'codex_memories': 'memories', 'codex_rules': 'rules', 'codex_skills': 'skills',
               'codex_plugins': 'plugins'}
ITEM_FIELDS = {'codex_skill': 'content', 'codex_plugin': 'manifest'}


def _root(scan: WorkspaceScan, path: Path) -> str:
    """'present' to list *path*, 'absent' when it is confirmed not there, 'lost' when it cannot be listed."""
    try:
        mode = path.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        return 'absent'
    except OSError as exc:
        scan.discovery_errors.append((path, exc))
        return 'lost'
    if not stat.S_ISDIR(mode):
        scan.discovery_errors.append((path, NotADirectoryError(f'{path.name} is not a directory')))
        return 'lost'
    return 'present'


def _kind(scan: WorkspaceScan, entry: Path) -> Optional[str]:
    """'dir' (descended, never through a symlink), 'file' (a file or a link to one) or None (skipped or lost)."""
    try:
        mode = entry.lstat().st_mode
        if stat.S_ISLNK(mode):
            mode = entry.stat().st_mode
            return 'file' if stat.S_ISREG(mode) else None
    except OSError as exc:
        scan.discovery_errors.append((entry, exc))
        return None
    return 'dir' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else None


def _files(scan: WorkspaceScan, root: Path, select: Callable[[Path], bool], *, recursive: bool) -> List[Path]:
    """The files *select* keeps under *root*, in path order; each is a candidate of the receipt."""
    found: List[Path] = []
    pending = [root]
    while pending:
        for entry in scan.entries(pending.pop()):
            kind = _kind(scan, entry)
            if kind == 'dir' and recursive:
                pending.append(entry)
            elif kind == 'file' and select(entry):
                found.append(entry)
    found.sort()
    scan.candidates.update(to_posix(path) for path in found)
    return found


def _text(scan: WorkspaceScan, path: Path) -> Optional[Tuple[str, int]]:
    """The entry's text (decode repairs recorded) and size, or None when it was lost."""
    try:
        text = scan.read_text(path)
        return text, path.stat().st_size
    except _ENTRY_ERRORS as exc:
        scan.entry_errors.append((path, exc))
        return None


def _base(result_type: str, source: Path, source_type: str) -> Dict[str, Any]:
    return dict(ResultBuilder.create(result_type=result_type, source=to_posix(source), source_type=source_type,
                                     contract_version=CONTRACT_VERSION))


def _attach(scan: WorkspaceScan, result: Dict[str, Any], state: str) -> Dict[str, Any]:
    scan.attach(result)
    result['meta']['workspace_analysis']['source_absent'] = state == 'absent'
    return result


def _lost(scan: WorkspaceScan) -> int:
    return len(scan.discovery_errors) + len(scan.entry_errors)


def _files_list(codex_home: Path, name: str, select, *, recursive: bool, result_type: str) -> Dict[str, Any]:
    directory = codex_home / name
    scan = WorkspaceScan(count_rule=WORKSPACE_RULE)
    state = _root(scan, directory)
    rows: List[Dict[str, Any]] = []
    for path in _files(scan, directory, select, recursive=recursive) if state == 'present' else ():
        read = _text(scan, path)
        if read is not None:
            rows.append({'path': to_posix(path), 'name': path.name, 'size_bytes': read[1], 'content': read[0]})
            scan.complete(path)
    return _attach(scan, {**_base(result_type, directory, 'file'), name: rows, 'total': len(rows)}, state)


def get_memories(codex_home: Path) -> Dict[str, Any]:
    """Every file under ~/.codex/memories/ with its content."""
    return _files_list(codex_home, 'memories', lambda path: True, recursive=True, result_type='codex_memories')


def get_rules(codex_home: Path) -> Dict[str, Any]:
    """The *.rules files in ~/.codex/rules/ with their content."""
    return _files_list(codex_home, 'rules', lambda path: path.name.endswith('.rules'), recursive=False,
                       result_type='codex_rules')


def _parse_skill_frontmatter(content: str) -> Dict[str, Any]:
    """Extract YAML-ish frontmatter (name/description) from a SKILL.md file."""
    fm: Dict[str, Any] = {}
    if not content.startswith('---'):
        return fm
    end = content.find('\n---', 3)
    if end < 0:
        return fm
    for line in split_lines(content[3:end]):
        if ':' in line:
            k, _, v = line.partition(':')
            fm[k.strip()] = v.strip().strip('"')
    return fm


def _not_found(kind: str, noun: str, name: str, entries) -> MissingResourceError:
    """A named item that matches no definition is an invalid request naming what was searched (plan rule 9)."""
    names = [entry['name'] for entry in entries]
    shown = ', '.join(names[:10]) + (', ...' if len(names) > 10 else '')
    plural = '' if len(names) == 1 else 's'
    return MissingResourceError(f'{kind} not found: {name} (searched {len(names)} {noun}{plural}'
                                f'{": " + shown if names else ""})')


def _definitions(codex_home: Path, name: str, select, record) -> Tuple[WorkspaceScan, str, List[Dict[str, Any]]]:
    """Read every definition *select* keeps; *record* turns one into its list row plus its private payload."""
    scan = WorkspaceScan(count_rule=WORKSPACE_RULE)
    directory = codex_home / name
    state = _root(scan, directory)
    rows = []
    for path in _files(scan, directory, select, recursive=True) if state == 'present' else ():
        read = _text(scan, path)
        if read is None:
            continue
        try:
            row = record(path, read[0])
        except _ENTRY_ERRORS as exc:
            scan.entry_errors.append((path, exc))
            continue
        rows.append(row)
        scan.complete(path)
    return scan, state, rows


def _named(scan, state, rows, base, *, kind, noun, item, payload) -> Dict[str, Any]:
    """The named definition, an incomplete lookup (exit 3) or the invalid request of one that is not there."""
    match = next((row for row in rows if row['name'] == item), None)
    if match is None and not _lost(scan):
        raise _not_found(kind.title(), noun, item, rows)
    result = {**base, 'type': f'codex_{kind}', 'name': item}
    if match is None:
        result['error'] = (f'{kind.title()} lookup incomplete: {item}; {_lost(scan)} {noun} source(s) could not be '
                           'read. Decisions: JSON meta.workspace_analysis.')
    else:
        result.update(source=match['path'], source_type='file', name=match['name'], **payload(match))
    return _attach(scan, result, state)


def get_skills(codex_home: Path, resource: str) -> Dict[str, Any]:
    """List or read skill definitions from ~/.codex/skills/**/SKILL.md."""
    contents: Dict[str, str] = {}

    def record(path, text):
        fm = _parse_skill_frontmatter(text)
        contents[to_posix(path)] = text
        return {'name': fm.get('name') or path.parent.name, 'description': fm.get('description', ''),
                'path': to_posix(path)}
    scan, state, rows = _definitions(codex_home, 'skills', lambda path: path.name == 'SKILL.md', record)
    base = _base('codex_skills', codex_home / 'skills', 'directory')
    item = resource.partition('/')[2].strip()
    if item:
        return _named(scan, state, rows, base, kind='skill', noun='skill definition', item=item,
                      payload=lambda row: {'description': row['description'], 'content': contents[row['path']]})
    return _attach(scan, {**base, 'skills': rows, 'total': len(rows)}, state)


def _manifest(text: str) -> Dict[str, Any]:
    manifest = json.loads(text)
    if not isinstance(manifest, dict):
        raise ValueError('plugin manifest is not a JSON object')
    return manifest


def get_plugins(codex_home: Path, resource: str) -> Dict[str, Any]:
    """List or read installed plugin manifests: ~/.codex/plugins/cache/**/.codex-plugin/plugin.json."""
    manifests: Dict[str, Dict[str, Any]] = {}

    def record(path, text):
        manifest = _manifest(text)
        manifests[to_posix(path)] = manifest
        return {'name': manifest.get('name', path.parent.parent.name), 'version': manifest.get('version', ''),
                'description': manifest.get('description', ''), 'path': to_posix(path)}
    scan, state, rows = _definitions(
        codex_home, 'plugins', lambda path: path.name == 'plugin.json' and path.parent.name == '.codex-plugin', record)
    base = _base('codex_plugins', codex_home / 'plugins', 'directory')
    item = resource.partition('/')[2].strip()
    if item:
        return _named(scan, state, rows, base, kind='plugin', noun='plugin manifest', item=item,
                      payload=lambda row: {'manifest': manifests[row['path']]})
    return _attach(scan, {**base, 'plugins': rows, 'total': len(rows)}, state)


# --- execution facts and the answer's requirements (qualification.RESOURCE_OWNERS) -----------------------------

def execution_facts(result):
    return workspace_execution_facts(result)


def _source(adapter, expected_type) -> Path:
    names = {'codex_memories': 'memories', 'codex_rules': 'rules', 'codex_skills': 'skills', 'codex_skill': 'skills',
             'codex_plugins': 'plugins', 'codex_plugin': 'plugins'}
    home: Path = adapter.CODEX_HOME
    return home / names[expected_type]


def _item_error(adapter, result, expected_type, prior_facts):
    from ....utils.workspace_scan import workspace_proof_error
    proof = result.get('meta', {}).get('workspace_analysis')
    error = workspace_proof_error(proof, label='Codex')
    if error:
        return error
    if prior_facts is None:
        adapter._workspace_proof = deepcopy(proof)
    if proof != adapter._workspace_proof:
        return 'Codex presentation cannot change workspace acquisition decisions'
    if result.get('error'):
        return None if proof['failed_operations'] else 'Codex lookup diagnostic without lost input'
    if not isinstance(result.get('name'), str) or ITEM_FIELDS[expected_type] not in result:
        return 'Codex workspace item missing its definition'
    if not result.get('source', '').startswith(to_posix(_source(adapter, expected_type)) + '/'):
        return 'Codex workspace item changed its definition source'
    return None


def answer_requirement_error(adapter, result, expected_type, prior_facts):
    proof = result.get('meta', {}).get('workspace_analysis')
    if not isinstance(proof, dict) or type(proof.get('source_absent')) is not bool:
        return 'Codex workspace answer missing its source-absent decision'
    if expected_type in ITEM_FIELDS:
        return _item_error(adapter, result, expected_type, prior_facts)
    if result.get('source') != to_posix(_source(adapter, expected_type)):
        return 'Codex workspace answer changed its directory source identity'
    if proof['source_absent'] and (proof['candidate_entries'] or result.get(LIST_FIELDS[expected_type])):
        return 'Codex workspace answer lists entries of an absent directory'
    return workspace_list_error(adapter, result, LIST_FIELDS[expected_type], prior_facts, label='Codex')
