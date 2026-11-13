"""Measured exact/prefix Markdown lookup, including existing ambiguity responses."""
import stat
from glob import has_magic
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Dict

from .workspace_scan import WorkspaceScan, _proof_error


class MarkdownLookup(WorkspaceScan):
    def __init__(self):
        super().__init__()
        self.resolution = 'unresolved'
        self.selected_source = ''
        self.matches: list[str] = []

    def resolve(self, directory, name):
        if has_magic(name):
            return self._prefix(directory, name)
        path = directory / name
        if not path.suffix:
            path = directory / (name + '.md')
        try:
            path.stat()
        except (FileNotFoundError, NotADirectoryError):
            return self._prefix(directory, name)
        except OSError as exc:
            self.discovery_errors.append((path, exc))
            return None
        return self.select(path, 'exact')

    def select(self, path, resolution):
        self.resolution = resolution
        self.selected_source = str(path)
        self.candidates.add(str(path))
        return path

    def _prefix(self, directory, name):
        if not self.directory(directory, required=True):
            return None
        pattern = Path(f'{name}*.md')
        if pattern.is_absolute():
            raise NotImplementedError('Non-relative patterns are unsupported')
        matches = sorted(set(self._glob(directory, pattern.parts)))
        if len(matches) == 1:
            return self.select(matches[0], 'prefix')
        if matches:
            self.resolution = 'ambiguous'
            self.matches = [p.stem for p in matches]
            self.candidates.update(str(p) for p in matches)
            self.completed.update(self.candidates)  # names, not bodies, are required for ambiguity
            return self.matches
        self.resolution = 'missing' if not self.discovery_errors else 'unresolved'
        self.request_rejected = not self.discovery_errors
        return None

    def _glob(self, directory, parts):
        """Path.glob's segment matching with observable directory acquisition errors.

        Recursive ** does not follow directory symlinks, matching the existing glob.
        Literal directory segments may follow symlinks, as before.
        """
        segment, *rest = parts
        if segment == '..':
            yield from self._glob(directory / '..', rest)
            return
        if segment == '**':
            yield from self._glob(directory, rest)
        for path in self.entries(directory):
            if segment != '**' and not fnmatchcase(path.name, segment):
                continue
            if not rest:
                yield path
            elif self._descend(path, follow=segment != '**'):
                yield from self._glob(path, parts if segment == '**' else rest)

    def _descend(self, path, *, follow):
        try:
            return stat.S_ISDIR(path.stat(follow_symlinks=follow).st_mode)
        except (FileNotFoundError, NotADirectoryError):
            return False
        except OSError as exc:
            self.discovery_errors.append((path, exc))
            return False

    def read(self, path, result):
        try:
            result['content'] = self.read_text(path)
            self.complete(path)
            result['modified'] = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds')
        except (OSError, ValueError, OverflowError) as exc:
            self.entry_errors.append((path, exc))
            result['error'] = str(exc)

    def attach(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result = super().attach(result)
        result['meta']['workspace_analysis']['lookup'] = {
            'resolution': self.resolution, 'source': self.selected_source,
            'matches': list(self.matches),
        }
        return result


def lookup_requirement_error(adapter, result, expected_type, prior_facts):
    from copy import deepcopy
    proof = result.get('meta', {}).get('workspace_analysis')
    error = _proof_error(proof)
    if error:
        return error
    if prior_facts is None:
        adapter._workspace_lookup_proof = deepcopy(proof)
    if proof != adapter._workspace_lookup_proof:
        return 'Claude presentation cannot change Markdown lookup decisions'
    return _resolution_error(result, expected_type, proof, prior_facts)


def _resolution_error(result, expected_type, proof, prior_facts):
    lookup = proof.get('lookup', {})
    resolution = lookup.get('resolution')
    if resolution == 'ambiguous':
        return _ambiguity_error(result, expected_type, lookup, prior_facts)
    if result.get('type') != expected_type:
        return 'Claude Markdown answer changed its resolution variant'
    if resolution in ('exact', 'prefix'):
        if result.get('source') != lookup.get('source') or result.get('source_type') != 'file':
            return 'Claude Markdown answer disagrees with selected file identity'
        if proof['analyzed_entries'] and not isinstance(result.get('content'), str):
            return 'Claude Markdown answer missing observed content'
    elif resolution not in ('missing', 'unresolved'):
        return 'Claude Markdown answer missing resolution decisions'
    return None


def _ambiguity_error(result, expected_type, lookup, prior_facts):
    matches = result.get('matches')
    if (result.get('type') != expected_type + 's' or result.get('ambiguous') is not True
            or not isinstance(matches, list) or not lookup.get('matches')
            or any(name not in lookup['matches'] for name in matches)
            or (prior_facts is None and matches != lookup['matches'])):
        return 'Claude Markdown ambiguity answer disagrees with source decisions'
    return None
