"""One answer to "does git ignore this path?" for every walker (BACK-1485, BACK-1386).

reveal used to answer it with a pattern matcher over the scan root's
``.gitignore`` alone. That matcher was wrong in both directions:

- It dropped files git keeps. git never ignores a *tracked* file, but a pattern
  matcher cannot know tracked status (tia's ``**/env/`` dropped committed
  ``config/env/*``), and it read ``!pattern`` negations as plain patterns
  (a private ops repo's ``*.sql`` + ``!docs/database/procedures/*.sql`` dropped all
  six committed procedures). Measured: 19,292 tracked files dropped in tia,
  6,204 in that ops repo.
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

A host request (``request_cache.host_request``) revalidates on entry (BACK-2117): the
directory-to-root map is forgotten (a ``git init`` between requests), and a repository's
entry survives only while it is younger than the TTL and a stat stamp of the files that can
change the answer is unchanged: the root and every known nested ``.gitignore``,
``info/exclude``, the index (tracked files are never ignored), the repository config and the
global config files, and the excludes file (taken only inside a request: a CLI run runs one
``git`` call per repository, as before). Inside a request an entry is not expired, so one
request sees one answer. Not stamped, so bounded by the TTL: a new ignored file, a
``.gitignore`` created after the entry was built, a system-level ``/etc/gitconfig`` edit.
Memory: one entry per repository touched (the ignored untracked paths, collapsed to
directories, plus a stamp of about ten ``(path, mtime, size)`` tuples and the nested
``.gitignore`` files); the directory map is emptied at every request.
"""

import functools
import logging
import os
import re
import stat as stat_mod
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple, Union

from .lines import split_lines
from .request_cache import in_host_request, register_request_cache

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 10.0
_GIT_TIMEOUT_S = 30

PathLike = Union[str, 'os.PathLike[str]']


# --------------------------------------------------------------------------
# git-backed repository ignore sets
# --------------------------------------------------------------------------

class _RepoIgnores:
    """The ignored untracked paths of one work tree, relative to its root."""

    __slots__ = ('files', 'dirs', 'loaded_at', 'stamp')

    def __init__(self, files: frozenset, dirs: frozenset, loaded_at: float):
        self.files = files
        self.dirs = dirs
        self.loaded_at = loaded_at
        # (path, mtime_ns, size) of the files that decide the answer, taken BEFORE the
        # listing so an edit that races the load shows as a change; None when git could not
        # name them, which makes the entry live for one request only.
        self.stamp: Optional[Tuple[Tuple[str, Optional[Tuple[int, int]]], ...]] = None

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


def _run_git(root: str, *args: str) -> Optional['subprocess.CompletedProcess[bytes]']:
    """Run ``git *args`` in *root*; None when git cannot be run at all."""
    try:
        return subprocess.run(['git', *args], cwd=root, capture_output=True,
                              timeout=_GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug('gitignore: git unavailable for %s (%s); using patterns', root, exc)
        return None


def _load_repo(root: str) -> Optional[_RepoIgnores]:
    """Ask git for *root*'s ignored untracked paths; None when git can't say."""
    proc = _run_git(root, 'ls-files', '-z', '--others', '--ignored',
                    '--exclude-standard', '--directory')
    if proc is None:
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


def _stamp_paths(root: str) -> Optional[List[str]]:
    """The files whose content can change what git ignores in *root*; None when git can't say."""
    where = _run_git(root, 'rev-parse', '--git-path', 'info/exclude', '--git-path', 'index',
                     '--git-path', 'config')
    if where is None or where.returncode != 0:
        return None
    paths = [os.path.join(root, line) for line in split_lines(os.fsdecode(where.stdout)) if line]
    # Nested ignore files at the time of the load (tracked, or untracked and not ignored).
    nested = _run_git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard',
                      '--', ':(glob)**/.gitignore')
    if nested is None or nested.returncode != 0:
        return None
    paths.extend(os.path.join(root, os.fsdecode(raw)) for raw in nested.stdout.split(b'\0') if raw)
    excludes = _run_git(root, 'config', '--path', '--get', 'core.excludesFile')
    if excludes is None or excludes.returncode not in (0, 1):  # 1: the key is unset
        return None
    configured = os.fsdecode(excludes.stdout).strip()
    if configured:
        paths.append(os.path.join(root, configured))
    else:  # git's default global excludes file
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
        paths.append(os.path.join(base, 'git', 'ignore'))
    home = os.path.expanduser('~')
    global_config = os.environ.get('GIT_CONFIG_GLOBAL')
    paths.extend([global_config] if global_config else [
        os.path.join(home, '.gitconfig'),
        os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.join(home, '.config'), 'git', 'config')])
    paths.append(os.path.join(root, '.gitignore'))
    return list(dict.fromkeys(paths))


def _stat_stamp(paths) -> Tuple[Tuple[str, Optional[Tuple[int, int]]], ...]:
    """(path, (mtime_ns, size)) per path; (path, None) for a path that does not exist."""
    stamp: List[Tuple[str, Optional[Tuple[int, int]]]] = []
    for path in paths:
        try:
            st = os.stat(path)
            # A device file (GIT_CONFIG_GLOBAL=/dev/null) has no content to compare, and its mtime
            # moves whenever any process writes to it (macOS): stamp it as present, not by time.
            stamp.append((path, (st.st_mtime_ns, st.st_size) if stat_mod.S_ISREG(st.st_mode) else (0, 0)))
        except OSError:
            stamp.append((path, None))
    return tuple(stamp)


def _repo_ignores(root: str) -> Optional[_RepoIgnores]:
    now = time.monotonic()
    in_request = in_host_request()
    with _LOCK:
        hit = _REPO_CACHE.get(root)
        # A host request revalidated its entries on entry (_begin_request): inside it an
        # entry does not expire, so one request sees one answer.
        if hit is not None and (in_request or now - hit[0] < _CACHE_TTL_S):
            return hit[1]
    # Only a host request ever revalidates a stamp; a one-shot run does not pay for one.
    paths = _stamp_paths(root) if in_request else None
    stamp = _stat_stamp(paths) if paths is not None else None
    loaded = _load_repo(root)
    if loaded is not None:
        loaded.stamp = stamp
    with _LOCK:
        _REPO_CACHE[root] = (now, loaded)
    return loaded


def _begin_request() -> None:
    """Host request entry: forget the directory map, keep only entries that are provably current.

    An entry is kept while it is younger than the TTL and its stamp is unchanged. A failed
    listing (None) and an entry git could not stamp are dropped: they are retried.
    """
    now = time.monotonic()
    with _LOCK:
        _ROOT_CACHE.clear()
        for root, (loaded_at, repo) in tuple(_REPO_CACHE.items()):
            keep = (repo is not None and repo.stamp is not None and now - loaded_at < _CACHE_TTL_S
                    and _stat_stamp([path for path, _ in repo.stamp]) == repo.stamp)
            if not keep:
                del _REPO_CACHE[root]


register_request_cache('gitignore', _begin_request)


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
    prefix = '^' if anchored else '^(?:.*/)?'
    rx = glob_path_regex(line.lstrip('/'))
    return _Rule(re.compile(prefix + rx + '$', re.DOTALL), negate, dir_only)


def glob_path_regex(pattern: str) -> str:
    """Translate a '/'-separated glob to an unanchored regex body.

    `*`, `?` and `[...]` match within one path segment; a whole `**` segment matches zero or
    more segments (`a/**/b`, `**/b`, `a/**`). The caller adds the anchors: `.gitignore` lines
    and `.reveal.yaml` `overrides.files` (`config.glob_match`) both compile through here.
    """
    parts = pattern.split('/')
    rx = ''
    for i, seg in enumerate(parts):
        last = i == len(parts) - 1
        if seg == '**':
            rx += '.*' if last else '(?:.*/)?'
        else:
            rx += _segment_regex(seg) + ('' if last else '/')
    return rx


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


class PatternSet:
    """``--exclude`` and REVEAL_IGNORE / config ``ignore:`` patterns, in gitignore(5) syntax.

    One syntax for every user-written skip pattern (BACK-1576): a bare name (``fixtures``,
    ``*.min.js``) matches at any depth, a pattern with a slash (``src/gen``, ``app/*``) is
    anchored at the root it is matched against, a trailing ``/`` matches directories only,
    ``**`` spans directories and ``!`` re-includes. As in git, a path under a matched
    directory is matched. Before this, three matchers each read patterns their own way, so
    ``--exclude skipme`` hid ``sub/skipme/`` in the tree but not in ``check``, and
    ``--exclude sub/skipme`` did the reverse.
    """

    __slots__ = ('rules', 'negates')

    def __init__(self, patterns: Tuple[str, ...]):
        self.rules = [r for r in (compile_gitignore_line(p) for p in patterns) if r is not None]
        self.negates = any(r.negate for r in self.rules)

    def _match(self, rel: str, is_dir: bool) -> bool:
        verdict = False
        for rule in self.rules:
            if (is_dir or not rule.dir_only) and rule.regex.match(rel):
                verdict = not rule.negate
        return verdict

    def matches(self, rel: str, is_dir: bool = False) -> bool:
        """True if the path *rel* (posix, relative to the patterns' root) is matched."""
        if not self.rules or rel in ('', '.'):
            return False
        segments = rel.split('/')
        for depth in range(1, len(segments)):
            if self._match('/'.join(segments[:depth]), True):
                return True
        return self._match(rel, is_dir)

    def covers_dir(self, rel: str) -> bool:
        """True if everything under directory *rel* is matched, so a walk can prune it:
        the directory itself matches, or any child would (``app/*``, ``vendor/**``) and no
        ``!`` rule could re-include one."""
        if self.matches(rel, True):
            return True
        return not self.negates and self.matches(rel + '/__reveal_probe__', False)


@functools.lru_cache(maxsize=64)
def pattern_set(patterns: Tuple[str, ...]) -> PatternSet:
    """The compiled ``PatternSet`` for *patterns* (a run uses a handful of pattern lists)."""
    return PatternSet(patterns)


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
