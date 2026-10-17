"""Opt-in, command-local attribution for owned full-source parser artifacts.

This observes existing requests and builds; it retains neither source nor trees
and changes no parser cache keys. A tree-sitter attempt counts the compatibility
wrapper call; its internal native string/bytes retries are excluded. Direct validation/snippet parser bypasses and
third-party generated code are outside this owner, not counted as target work.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import platform
import sys
from typing import Any, Iterable, Iterator, Literal, Optional, Union

Domain = Literal['fullsource', 'snippet', 'validation']
Outcome = Literal['built', 'cached', 'failed']
PathArg = Union[str, os.PathLike[str]]


class ParseAttributionError(ValueError):
    """A capture cannot establish complete parser attribution."""


@dataclass(frozen=True)
class ParseEvent:
    event: Literal['request', 'attempt', 'artifact', 'failure', 'outcome']
    request_id: int
    parser: str
    domain: Domain
    filename: Optional[str]
    scope: Literal['target', 'external', 'unattributed']
    source_hash: str
    source_length: int
    pid: int
    attempt_id: Optional[int] = None
    parsed_hash: Optional[str] = None
    phase: Optional[str] = None
    outcome: Optional[Outcome] = None
    error: Optional[str] = None


def _digest(source: str) -> str:
    return sha256(source.encode('utf-8', 'surrogatepass')).hexdigest()


def _package_version(package: str) -> Optional[str]:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


@dataclass
class ParseCapture:
    root: Path
    targets: Optional[frozenset[Path]] = None
    events: list[ParseEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=lambda: {
        'parser_versions': {
            'python.ast': platform.python_version(),
            'tree-sitter-language-pack': _package_version('tree-sitter-language-pack'),
            'tree-sitter': _package_version('tree-sitter'),
        },
        'pid': os.getpid(),
        'scope': 'Owned parser-seam requests and physical artifacts; bypass parses excluded.',
    })
    _next_request: int = 0

    def request(self, parser: str, source: str, filename: Optional[PathArg], domain: Domain) -> ParseEvent:
        if domain not in ('fullsource', 'snippet', 'validation'):
            raise ParseAttributionError(f'unknown parse domain: {domain!r}')
        path = None if filename is None or str(filename) == '' or str(filename).startswith('<') else Path(filename).resolve()
        if path is None:
            scope: Literal['target', 'external', 'unattributed'] = 'unattributed'
        else:
            included = path in self.targets if self.targets is not None else path.is_relative_to(self.root)
            scope = 'target' if included else 'external'
        self._next_request += 1
        event = ParseEvent('request', self._next_request, parser, domain,
                           path.as_posix() if path is not None else None, scope,
                           _digest(source), len(source.encode('utf-8', 'surrogatepass')), os.getpid())
        self.events.append(event)
        return event

    def validate(self) -> None:
        """Reject unattributed full-source work and incomplete request/attempt ledgers."""
        requests = [event for event in self.events if event.event == 'request']
        identifiers = {event.request_id for event in requests}
        if len(identifiers) != len(requests):
            raise ParseAttributionError('duplicate request identifier')
        grouped: dict[int, list[ParseEvent]] = {identifier: [] for identifier in identifiers}
        for event in self.events:
            if event.request_id not in grouped:
                raise ParseAttributionError('event without a request')
            grouped[event.request_id].append(event)
        for request in requests:
            if request.domain == 'fullsource' and request.filename is None:
                raise ParseAttributionError('fullsource request requires a known filename')
            _validate_request(grouped[request.request_id])


def _validate_request(events: list[ParseEvent]) -> None:
    _validate_event_identity(events)
    outcomes = [event for event in events if event.event == 'outcome']
    if len(outcomes) != 1:
        raise ParseAttributionError('each request requires exactly one outcome')
    artifacts = [event for event in events if event.event == 'artifact']
    attempts = [event for event in events if event.event == 'attempt']
    outcome = outcomes[0].outcome
    if outcome == 'built' and not artifacts:
        raise ParseAttributionError('built outcome without an artifact')
    if outcome == 'cached' and (artifacts or attempts):
        raise ParseAttributionError('cached outcome with physical parse work')
    if outcome not in ('built', 'cached', 'failed'):
        raise ParseAttributionError('missing request outcome value')
    if (outcome == 'failed') != (outcomes[0].error is not None):
        raise ParseAttributionError('request outcome disagrees with failure')
    _validate_attempts(events, attempts)


def _validate_attempts(events: list[ParseEvent], attempts: list[ParseEvent]) -> None:
    identifiers = {event.attempt_id for event in attempts}
    if len(identifiers) != len(attempts) or None in identifiers:
        raise ParseAttributionError('invalid parse attempt identifiers')
    completions = [event for event in events if event.event in ('artifact', 'failure')]
    if any(event.attempt_id not in identifiers for event in completions):
        raise ParseAttributionError('parse completion without an attempt')
    for attempt in attempts:
        finished = [event for event in completions if event.attempt_id == attempt.attempt_id]
        if len(finished) != 1:
            raise ParseAttributionError('each parse attempt requires one artifact or failure')
        terminal = finished[0]
        if (terminal.parsed_hash, terminal.phase) != (attempt.parsed_hash, attempt.phase):
            raise ParseAttributionError('parse completion disagrees with attempt identity')
        if (terminal.event == 'failure') != (terminal.error is not None):
            raise ParseAttributionError('parse completion disagrees with failure')


def _request_identity(event: ParseEvent) -> tuple:
    return (event.request_id, event.parser, event.domain, event.filename, event.scope,
            event.source_hash, event.source_length, event.pid)


def _validate_event_identity(events: list[ParseEvent]) -> None:
    if events[0].event != 'request' or events[-1].event != 'outcome':
        raise ParseAttributionError('request and outcome must bound the event sequence')
    identity = _request_identity(events[0])
    if any(_request_identity(event) != identity for event in events):
        raise ParseAttributionError('event disagrees with request identity')


@dataclass
class _Request:
    capture: ParseCapture
    event: ParseEvent
    attempts: int = 0
    artifacts: int = 0


_CAPTURE: ContextVar[Optional[ParseCapture]] = ContextVar('reveal_parse_capture', default=None)
_REQUEST: ContextVar[Optional[_Request]] = ContextVar('reveal_parse_request', default=None)


def capture_enabled() -> bool:
    return _CAPTURE.get() is not None


@contextmanager
def capture_parses(target_root: PathArg, *, targets: Optional[Iterable[PathArg]] = None) -> Iterator[ParseCapture]:
    """Capture this context only; target manifest entries may be relative to root.

    A failed command retains its original exception and ledger for an explicit
    validate(). A clean exit validates automatically. All contexts reset either way.
    """
    root = Path(target_root).resolve()
    manifest = None if targets is None else frozenset(
        (root / Path(path)).resolve() for path in targets)
    capture = ParseCapture(root, manifest)
    capture_token = _CAPTURE.set(capture)
    request_token = _REQUEST.set(None)
    complete = False
    try:
        yield capture
        complete = True
    finally:
        _REQUEST.reset(request_token)
        _CAPTURE.reset(capture_token)
        if complete:
            capture.validate()


@contextmanager
def parse_request(parser: str, source: str, filename: Optional[PathArg], domain: Domain) -> Iterator[None]:
    capture = _CAPTURE.get()
    if capture is None:
        yield
        return
    request = _Request(capture, capture.request(parser, source, filename, domain))
    token = _REQUEST.set(request)
    complete = False
    try:
        yield
        complete = True
    finally:
        outcome: Outcome = ('built' if request.artifacts else 'cached') if complete else 'failed'
        error = sys.exc_info()[0]
        capture.events.append(replace(request.event, event='outcome', outcome=outcome,
                                      error=None if complete or error is None else error.__name__))
        _REQUEST.reset(token)


@contextmanager
def parse_attempt(source: str, phase: str) -> Iterator[None]:
    request = _REQUEST.get()
    if request is None:
        if capture_enabled():
            raise ParseAttributionError('physical parse attempt without a seam request')
        yield
        return
    request.attempts += 1
    event = replace(request.event, event='attempt', attempt_id=request.attempts,
                    parsed_hash=_digest(source), phase=phase, pid=os.getpid())
    request.capture.events.append(event)
    complete = False
    try:
        yield
        complete = True
    finally:
        error = sys.exc_info()[0]
        request.capture.events.append(replace(event, event='artifact' if complete else 'failure',
                                             error=None if complete or error is None else error.__name__))
        if complete:
            request.artifacts += 1
