"""Qualified, request-local execution of the existing transcript lookup strategies."""
import os
import json
import stat
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ...errors import RequestValidationError


class TranscriptNotFoundError(RequestValidationError, FileNotFoundError):
    """A healthy lookup found no transcript; qualified transports classify the request."""


Failures = List[Tuple[Path, BaseException]]
TimestampReader = Callable[[Path, Failures, Failures], str]


class ConversationDiscovery:
    """Retain discovery loss instead of letting glob suppression prove absence."""

    def __init__(self, base: Path, name: str, timestamp: TimestampReader, short_id: bool):
        self.base, self.name = base, name
        self.timestamp, self.short_id = timestamp, short_id
        self.failures: Failures = []
        self.recoveries: Failures = []
        self.other_transcripts: List[Path] = []
        self._directory_state: Dict[Path, bool] = {}
        self._file_lists: Dict[Path, List[Path]] = {}

    def _is_directory(self, path: Path) -> bool:
        if path not in self._directory_state:
            try:
                self._directory_state[path] = stat.S_ISDIR(path.stat().st_mode)
            except OSError as exc:
                self.failures.append((path, exc))
                self._directory_state[path] = False
        return self._directory_state[path]

    def _files(self, directory: Path) -> List[Path]:
        if directory not in self._file_lists:
            files: List[Path] = []
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        path = directory / entry.name
                        if path.match('*.jsonl'):
                            files.append(path)
            except OSError as exc:
                self.failures.append((directory, exc))
            self._file_lists[directory] = files
        return self._file_lists[directory]

    def _named_match(self, projects: List[Path]) -> Optional[Path]:
        named = [p for p in projects if self.name in p.name and self._is_directory(p)]
        named.sort(key=lambda p: not (p.name == self.name or p.name.endswith('-' + self.name)))
        for directory in named:
            files = [p for p in self._files(directory) if not p.stem.startswith('agent-')]
            if files:
                files.sort(key=lambda p: (self.timestamp(p, self.failures, self.recoveries), p.name))
                self.other_transcripts = files[1:]
                return files[0]
        return None

    def _exact_match(self, directories: List[Path]) -> Optional[Path]:
        for directory in directories:
            path = directory / f'{self.name}.jsonl'
            try:
                path.stat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                self.failures.append((path, exc))
                continue
            return path
        return None

    def _stem_match(self, directories: List[Path], matches: Callable[[str], bool]) -> Optional[Path]:
        for directory in directories:
            for path in self._files(directory):
                if matches(path.stem):
                    return path
        return None

    def find(self) -> Optional[Path]:
        if not self.name:
            return None
        try:
            projects = list(self.base.iterdir())
        except FileNotFoundError:
            return None
        named = self._named_match(projects)
        if named is not None:
            return named
        directories = [p for p in projects if self._is_directory(p)]
        exact = self._exact_match(directories)
        if exact is not None:
            return exact
        suffix = self._stem_match(directories, lambda stem: stem.endswith(self.name))
        if suffix is not None:
            return suffix
        if self.short_id:
            return self._stem_match(directories, lambda stem: stem.startswith(self.name))
        return None

    def receipt(self) -> dict:
        return {'failed_operations': len(self.failures), 'recovered_operations': len(self.recoveries),
                'count_rule': 'Distinct failure/recovery kinds per source in lookup and first-timestamp selection',
                'failures': _diagnostics(self.failures), 'recoveries': _diagnostics(self.recoveries)}


def _diagnostics(entries: Failures) -> list:
    return [{'source': str(path), 'cause': type(exc).__name__, 'message': str(exc)} for path, exc in entries]


def _report_once(entries: Optional[Failures], path: Path, exc: BaseException) -> None:
    if entries is not None and not any(p == path and type(e) is type(exc) for p, e in entries):
        entries.append((path, exc))


def _timestamp_value(record) -> Optional[str]:
    value = record.get('timestamp') if isinstance(record, dict) else None
    return value if isinstance(value, str) else None


def _line_timestamp(line: str, path: Path, failures: Optional[Failures],
                    recoveries: Optional[Failures]) -> Optional[str]:
    if not any('\udc80' <= ch <= '\udcff' for ch in line):
        return _timestamp_value(json.loads(line))
    raw = line.encode('utf-8', errors='surrogateescape')
    try:
        raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        # Preserve the old replacement-decoded key exactly, while locating loss in the
        # required timestamp field rather than unrelated text in an unselected transcript.
        repaired = _timestamp_value(json.loads(raw.decode('utf-8', errors='replace')))
        original = _timestamp_value(json.loads(line))
        _report_once(recoveries if original == repaired else failures, path, exc)
        return repaired
    return None


def first_timestamp(path: Path, *, errors_out: Optional[Failures] = None,
                    recovered_out: Optional[Failures] = None) -> str:
    """Existing first recorded timestamp key; absence/unreadability sorts last."""
    try:
        with open(path, 'r', encoding='utf-8', errors='surrogateescape') as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    timestamp = _line_timestamp(line, path, errors_out, recovered_out)
                except json.JSONDecodeError as exc:
                    _report_once(errors_out, path, exc)
                    continue
                if timestamp is not None:
                    return timestamp
    except OSError as exc:
        _report_once(errors_out, path, exc)
    return '~'
