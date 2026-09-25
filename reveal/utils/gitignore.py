"""One answer to "does git ignore this path?" for every walker (BACK-1485, BACK-1386).

reveal used to answer it with a pattern matcher over the scan root's
``.gitignore`` alone. That matcher was wrong in both directions:

- It dropped files git keeps. git never ignores a *tracked* file, but a pattern
  matcher cannot know tracked status (tia's ``**/env/`` dropped committed
  ``config/env/*``), and it read ``!pattern`` negations as plain patterns
  (sociamonials-ops ``*.sql`` + ``!docs/database/procedures/*.sql`` dropped all
  six committed procedures). Measured: 19,292 tracked files dropped in tia,
  6,204 in sociamonials-ops.
- It kept files git ignores: nested ``.gitignore`` files, ``.git/info/exclude``
  and the global excludes file were never read.

So the oracle asks git itself. Inside a work tree it runs, once per repository
root, ``git ls-files --others --ignored --exclude-standard --directory``: the
ignored *untracked* paths, with wholly-ignored directories collapsed to one
``dir/`` entry so a walk can prune them. Tracked files are never "others", so
they can never be reported as ignored.

Outside a work tree, or when git is unavailable or fails, a gitignore(5)
pattern matcher is the fallback: it reads ``.gitignore`` files from the anchor
directory down (plus ``.git/info/exclude`` when the anchor is a repository),
applies them last-match-wins with negation, and honors "a file under an
excluded directory cannot be re-included". It cannot know tracked status, which
is why it is only the fallback.

Each path is judged by the repository that contains its *parent* directory, so
a nested repository or submodule is judged by its own ignore rules, and a
nested repository the outer one ignores is pruned as a whole, as git does.

Results are cached per repository root for ``_CACHE_TTL_S`` seconds: one
``ls-files`` per repo per CLI run, while a long-lived host (the MCP server)
still sees files created since.
"""

import logging
import os
import re
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 10.0
_GIT_TIMEOUT_S = 30

PathLike = Union[str, 'os.PathLike[str]']


# --------------------------------------------------------------------------
# git-backed repository ignore sets
# --------------------------------------------------------------------------

class _RepoIgnores:
    """The ignored untracked paths of one work tree, relative to its root."""

    __slots__ = ('files', 'dirs', 'loaded_at')

    def __init__(self, files: frozenset, dirs: frozenset, loaded_at: float):
        self.files = files
        self.dirs = dirs
        self.loaded_at = loaded_at

    def ignored(self, rel: str, is_dir: bool) -> bool:
        if (rel in self.dirs) if is_dir else (rel in self.files):
            return True
        # An entry under a collapsed ignored directory is ignored too.
        cut = rel.rfind('/')
        while cut > 0:
            rel = rel[:cut]
            if rel in self.dirs:
                return True
            cut = rel.rfind('/')
        return False


_REPO_CACHE: Dict[str, Tuple[float, Optional[_RepoIgnores]]] = {}
_ROOT_CACHE: Dict[str, Optional[str]] = {}
_LOCK = threading.Lock()


def clear_cache() -> None:
    """Forget every cached repository answer (tests, long-lived hosts)."""
    with _LOCK:
        _REPO_CACHE.clear()
        _ROOT_CACHE.clear()


def _repo_root(directory: str) -> Optional[str]:
    """Nearest ancestor-or-self of *directory* holding a ``.git`` entry.

    ``.git`` may be a directory or, for worktrees and submodules, a file.
    """
    cached = _ROOT_CACHE.get(directory, False)
    if cached is not False:
        return cached  # type: ignore[return-value]
    root: Optional[str] = None
    probe = directory
    while True:
        if os.path.lexists(os.path.join(probe, '.git')):
            root = probe
            break
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    _ROOT_CACHE[directory] = root
    return root


def _load_repo(root: str) -> Optional[_RepoIgnores]:
    """Ask git for *root*'s ignored untracked paths; None when git can't say."""
    try:
        proc = subprocess.run(
            ['git', 'ls-files', '-z', '--others', '--ignored',
             '--exclude-standard', '--directory'],
            cwd=root, capture_output=True, timeout=_GIT_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug('gitignore: git unavailable for %s (%s); using patterns', root, exc)
        return None
    if proc.returncode != 0:
        logger.debug('gitignore: git ls-files failed in %s: %s', root,
                     proc.stderr.decode('utf-8', 'replace').strip())
        return None
    files, dirs = set(), set()
    for raw in proc.stdout.split(b'\0'):
        if not raw:
            continue
        entry = os.fsdecode(raw)
        if entry.endswith('/'):
            dirs.add(entry.rstrip('/'))
        else:
            files.add(entry)
    return _RepoIgnores(frozenset(files), frozenset(dirs), time.monotonic())


def _repo_ignores(root: str) -> Optional[_RepoIgnores]:
    now = time.monotonic()
    with _LOCK:
        hit = _REPO_CACHE.get(root)
        if hit is not None and now - hit[0] < _CACHE_TTL_S:
            return hit[1]
    loaded = _load_repo(root)
    with _LOCK:
        _REPO_CACHE[root] = (now, loaded)
    return loaded


# --------------------------------------------------------------------------
# gitignore(5) pattern fallback
# --------------------------------------------------------------------------

class _Rule:
    __slots__ = ('regex', 'negate', 'dir_only')

    def __init__(self, regex: 're.Pattern[str]', negate: bool, dir_only: bool):
        self.regex = regex
        self.negate = negate
        self.dir_only = dir_only


def _segment_regex(seg: str) -> str:
    """Translate one path segment's glob (no '/') to a regex fragment."""
    out: List[str] = []
    i, n = 0, len(seg)
    while i < n:
        c = seg[i]
        if c == '\\' and i + 1 < n:
            out.append(re.escape(seg[i + 1]))
            i += 2
            continue
        if c == '*':
            while i < n and seg[i] == '*':
                i += 1
            out.append('[^/]*')
            continue
        if c == '?':
            out.append('[^/]')
        elif c == '[':
            j = i + 1
            if j < n and seg[j] in '!^':
                j += 1
            if j < n and seg[j] == ']':
                j += 1
            while j < n and seg[j] != ']':
                j += 1
            if j >= n:
                out.append(re.escape(c))
            else:
                body = seg[i + 1:j]
                negated = body[:1] in ('!', '^')
                if negated:
                    body = body[1:]
                body = body.replace('\\', '\\\\')
                out.append('(?!/)[' + ('^' if negated else '') + body + ']')
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    return ''.join(out)


def compile_gitignore_line(line: str) -> Optional[_Rule]:
    """Compile one gitignore(5) line; None for blanks and comments."""
    line = line.rstrip('\r\n')
    # Trailing spaces are ignored unless escaped with a backslash.
    stripped = line.rstrip(' ')
    if stripped.endswith('\\') and len(stripped) < len(line):
        stripped += ' '
    line = stripped
    if not line or line.startswith('#'):
        return None
    negate = False
    if line.startswith('!'):
        negate, line = True, line[1:]
    elif line.startswith(('\\!', '\\#')):
        line = line[1:]
    dir_only = line.endswith('/')
    line = line.rstrip('/')
    if not line:
        return None
    # A slash at the start or in the middle anchors the pattern to the
    # .gitignore's own directory; otherwise it matches at any depth.
    anchored = '/' in line
    line = line.lstrip('/')
    parts = line.split('/')
    rx = ''
    for i, seg in enumerate(parts):
        last = i == len(parts) - 1
        if seg == '**':
            rx += '.*' if last else '(?:.*/)?'
        else:
            rx += _segment_regex(seg) + ('' if last else '/')
    prefix = '^' if anchored else '^(?:.*/)?'
    return _Rule(re.compile(prefix + rx + '$', re.DOTALL), negate, dir_only)


def _read_rules(path: str) -> List[_Rule]:
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            lines = fh.readlines()
    except OSError:
        return []
    return [r for r in (compile_gitignore_line(ln) for ln in lines) if r is not None]


class _PatternMatcher:
    """gitignore(5) semantics over the .gitignore files at and below *anchor*."""

    def __init__(self, anchor: str):
        self.anchor = anchor
        self._rules: Dict[str, List[_Rule]] = {}
        self._dir_verdicts: Dict[str, bool] = {}
        exclude = os.path.join(anchor, '.git', 'info', 'exclude')
        self._info_exclude = _read_rules(exclude) if os.path.isfile(exclude) else []

    def _rules_for(self, rel_dir: str) -> List[_Rule]:
        rules = self._rules.get(rel_dir)
        if rules is None:
            base = os.path.join(self.anchor, rel_dir) if rel_dir else self.anchor
            rules = _read_rules(os.path.join(base, '.gitignore'))
            self._rules[rel_dir] = rules
        return rules

    def _match(self, rel: str, is_dir: bool) -> bool:
        verdict = False
        # info/exclude ranks below every .gitignore; deeper files rank higher.
        for rule in self._info_exclude:
            if (is_dir or not rule.dir_only) and rule.regex.match(rel):
                verdict = not rule.negate
        segments = rel.split('/')
        for depth in range(len(segments)):
            base = '/'.join(segments[:depth])
            sub = '/'.join(segments[depth:])
            for rule in self._rules_for(base):
                if (is_dir or not rule.dir_only) and rule.regex.match(sub):
                    verdict = not rule.negate
        return verdict

    def ignored(self, rel: str, is_dir: bool) -> bool:
        segments = rel.split('/')
        # A path under an excluded directory cannot be re-included.
        for depth in range(1, len(segments)):
            ancestor = '/'.join(segments[:depth])
            verdict = self._dir_verdicts.get(ancestor)
            if verdict is None:
                verdict = self._match(ancestor, True)
                self._dir_verdicts[ancestor] = verdict
            if verdict:
                return True
        return self._match(rel, is_dir)


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def _rel_posix(path: str, root: str) -> Optional[str]:
    # Walks feed absolute paths under the root: slice instead of relpath,
    # which re-normalizes both arguments on every call.
    prefix = root if root.endswith(os.sep) else root + os.sep
    if path.startswith(prefix):
        rel = path[len(prefix):]
        return rel.replace(os.sep, '/') if rel else None
    try:
        rel = os.path.relpath(path, root)
    except ValueError:  # different drive on Windows
        return None
    if rel == '.' or rel.startswith('..'):
        return None
    return rel.replace(os.sep, '/')


class GitIgnoreFilter:
    """Judges paths under one scan root the way git would.

    ``ignored(path, is_dir)`` is the only query; walkers call it on each
    directory before descending (to prune) and on each file they would yield.
    Counters record what was skipped so callers can disclose it.
    """

    def __init__(self, scan_root: PathLike):
        self.scan_root = os.path.abspath(os.fspath(scan_root))
        self._fallbacks: Dict[str, _PatternMatcher] = {}
        self.skipped_files = 0
        self.skipped_dirs = 0
        self.modes: set = set()

    def _fallback(self, anchor: str) -> _PatternMatcher:
        matcher = self._fallbacks.get(anchor)
        if matcher is None:
            matcher = self._fallbacks[anchor] = _PatternMatcher(anchor)
        return matcher

    def _judge(self, abspath: str, is_dir: bool) -> bool:
        parent = os.path.dirname(abspath)
        root = _repo_root(parent)
        if root is not None:
            rel = _rel_posix(abspath, root)
            if rel is None:
                return False
            repo = _repo_ignores(root)
            if repo is not None:
                self.modes.add('git')
                return repo.ignored(rel, is_dir)
            self.modes.add('patterns')
            return self._fallback(root).ignored(rel, is_dir)
        rel = _rel_posix(abspath, self.scan_root)
        if rel is None:
            return False
        self.modes.add('patterns')
        return self._fallback(self.scan_root).ignored(rel, is_dir)

    def ignored(self, path: PathLike, is_dir: bool = False) -> bool:
        abspath = os.path.abspath(os.fspath(path))
        if self._judge(abspath, is_dir):
            if is_dir:
                self.skipped_dirs += 1
            else:
                self.skipped_files += 1
            return True
        return False

    def prune(self, root: PathLike, dirs: List[str]) -> None:
        """Drop ignored names from an ``os.walk`` *dirs* list, in place."""
        base = os.fspath(root)
        dirs[:] = [d for d in dirs if not self.ignored(os.path.join(base, d), is_dir=True)]


# --no-gitignore reaches every walker through this process-wide switch rather
# than a respect_gitignore kwarg threaded through each call chain (the same
# trade utils/exclusions.py made for --exclude). apply_global_flags() sets it
# from the parsed args; a URI's ?respect_gitignore= is applied around its
# dispatch with gitignore_scope().
_ENABLED = True


def set_gitignore_enabled(enabled: bool) -> None:
    global _ENABLED
    _ENABLED = bool(enabled)


def gitignore_enabled() -> bool:
    return _ENABLED


@contextmanager
def gitignore_scope(enabled: Optional[bool]):
    """Override the switch for the block (None leaves it alone), then restore."""
    global _ENABLED
    prev = _ENABLED
    if enabled is not None:
        _ENABLED = bool(enabled)
    try:
        yield
    finally:
        _ENABLED = prev


def parse_respect_gitignore(value: object) -> Optional[bool]:
    """A ?respect_gitignore= query value as a bool; None when absent."""
    if value is None:
        return None
    return str(value).strip().lower() not in ('false', '0', 'no', 'off')


def split_respect_gitignore(resource: str) -> Tuple[str, Optional[bool]]:
    """Split ``respect_gitignore=`` off a URI resource's query.

    Returns (resource without the key, its bool value or None). Every URI
    entry point (cli/routing/uri.handle_uri, api.query) consumes the key and
    applies it with gitignore_scope() for the whole dispatch, so every walker
    sees it -- and filter-style adapters (ast://, markdown://) never read it
    as a field filter that matches nothing.
    """
    path_part, sep, query = resource.partition('?')
    if not sep:
        return resource, None
    kept, value = [], None
    for part in query.split('&'):
        key, _, val = part.partition('=')
        if key == 'respect_gitignore':
            value = parse_respect_gitignore(val)
        elif part:
            kept.append(part)
    if value is None:
        return resource, None
    return (f"{path_part}?{'&'.join(kept)}" if kept else path_part), value


def respect_gitignore_param(query_params) -> bool:
    """An adapter's ?respect_gitignore= if given, else the process switch."""
    explicit = parse_respect_gitignore(query_params.get('respect_gitignore'))
    return _ENABLED if explicit is None else explicit


def gitignore_filter(scan_root: PathLike, respect_gitignore: Optional[bool] = None) -> Optional[GitIgnoreFilter]:
    """A filter for walks under *scan_root*, or None when gitignore is off.

    *respect_gitignore* None means "whatever the process switch says".
    Callers write ``if gi is not None and gi.ignored(p): continue`` so
    ``--no-gitignore`` costs nothing.
    """
    if respect_gitignore is None:
        respect_gitignore = _ENABLED
    return GitIgnoreFilter(scan_root) if respect_gitignore else None


def is_gitignored(path: PathLike, is_dir: bool = False) -> bool:
    """One-off query, anchored at the path's own directory when not in a repo."""
    abspath = os.path.abspath(os.fspath(path))
    return GitIgnoreFilter(os.path.dirname(abspath)).ignored(abspath, is_dir)
