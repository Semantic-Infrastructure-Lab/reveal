#!/usr/bin/env python3
"""Fail when the CHANGELOG misses a shipped task, or is not written for its readers.

Every `feat`/`fix`/`perf` commit since the last `vX.Y.Z` tag names its tasks as BACK-N
in the subject. Each of those ids must appear in the `## [Unreleased]` section of
CHANGELOG.md, or in scripts/changelog_coverage_skip.txt with a reason (internal work a
user never sees: CI, ratchets, test harnesses). A commit of those types with no id at
all is listed as a warning: nothing can be matched against it, so give it an id.

    python3 scripts/check_changelog_coverage.py            # exit 1 on a missing id or a style error
    python3 scripts/check_changelog_coverage.py --since v0.130.0

Style (the same section, "Writing CHANGELOG entries" in RELEASING.md): an entry longer than
MAX_ENTRY_CHARS or a section larger than MAX_SECTION_KB is an error, because the section
becomes the GitHub release notes and an upgrader reads the top of it. Internal vocabulary
("retains", "carrier", "seam", ...) is a warning: say what changed for the user instead.

Why: three days of worktree-agent rounds merged 314 commits and the changelog covered 49
of 116 task ids. The release-time checks (V011, test_changelog_release_headings) only
check that a heading exists, not that it says what shipped. The coverage rule alone then
produced 0.132.0's 201 entries (76 KB, 42 of 107 fixes in internal vocabulary): when every
task id must appear, one grouped entry plus a skip-file line is the way to cover a series.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_FILE = Path(__file__).with_name('changelog_coverage_skip.txt')
USER_VISIBLE = re.compile(r'^(feat|fix|perf)(\([^)]*\))?!?:')
TASK_ID = re.compile(r'BACK-\d+')
MAX_ENTRY_CHARS = 700    # one entry, continuation lines included; aim for two sentences
MAX_SECTION_KB = 40      # the section under [Unreleased] (it becomes the release notes)
INTERNAL_WORDS = re.compile(
    r'\b(retains?|carriers?|seams?|observations?|ratchets?|harness(?:es)?|binders?)\b', re.I)


def _git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True,
                          encoding='utf-8', timeout=60, check=True).stdout


def last_release_tag():
    tags = [t for t in _git('tag', '-l', 'v*').split() if re.fullmatch(r'v\d+\.\d+\.\d+', t)]
    return max(tags, key=lambda t: tuple(int(n) for n in t[1:].split('.')), default=None)


def unreleased_section(since=None):
    """Everything above the last release's heading: [Unreleased], and at release time the
    new `## [X.Y.Z]` section the prep commit moved those entries under."""
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    release = re.escape(since[1:]) if since and re.fullmatch(r'v\d+\.\d+\.\d+', since) else r'\d'
    match = re.search(r'^## \[Unreleased\]\n(.*?)(?=^## \[' + release + r')', text, re.S | re.M)
    return match.group(1) if match else ''


def entries(section):
    """Yield each top-level `- ` bullet with its wrapped continuation lines joined."""
    current = None
    for line in section.splitlines():
        if line.startswith('- '):
            if current is not None:
                yield current
            current = line
        elif current is not None and line.startswith(' ') and line.strip():
            current += ' ' + line.strip()
        elif current is not None:
            yield current
            current = None
    if current is not None:
        yield current


def style_problems(section):
    """Return (errors, warnings) about how the section reads; see the module docstring."""
    errors, warnings = [], []
    size_kb = len(section.encode('utf-8')) / 1024
    if size_kb > MAX_SECTION_KB:
        errors.append(f'section is {size_kb:.0f} KB, over {MAX_SECTION_KB} KB: group a series into one '
                      f'entry and list its task ids in {SKIP_FILE.name}')
    for entry in entries(section):
        head = entry[2:72]
        if len(entry) > MAX_ENTRY_CHARS:
            errors.append(f'entry too long ({len(entry)} > {MAX_ENTRY_CHARS} chars): {head}...')
        word = INTERNAL_WORDS.search(entry)
        if word:
            warnings.append(f"internal vocabulary '{word.group(0)}': {head}...")
    return errors, warnings


def skipped_ids():
    if not SKIP_FILE.exists():
        return set()
    lines = SKIP_FILE.read_text(encoding='utf-8').splitlines()
    return {m.group(0) for line in lines if not line.startswith('#')
            for m in [TASK_ID.match(line)] if m}


def uncovered(since):
    """Return (missing, idless): task id -> first commit subject, and commits with no id."""
    covered = set(TASK_ID.findall(unreleased_section(since))) | skipped_ids()
    missing, idless = {}, []
    for line in _git('log', f'{since}..HEAD', '--format=%h %s').splitlines():
        sha, _, subject = line.partition(' ')
        if not USER_VISIBLE.match(subject):
            continue
        ids = set(TASK_ID.findall(subject))
        if not ids:
            idless.append(line)
        for task in sorted(ids - covered):
            missing.setdefault(task, line)
    return missing, idless


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--since', help='base tag or commit (default: the last vX.Y.Z tag)')
    since = parser.parse_args(argv).since or last_release_tag()
    if not since:
        print('no release tag: nothing to compare')
        return 0
    missing, idless = uncovered(since)
    for line in idless:
        print(f'warning: feat/fix/perf commit without a BACK id: {line[:120]}')
    for task, line in sorted(missing.items(), key=lambda kv: int(kv[0][5:])):
        print(f'missing: {task} not in CHANGELOG [Unreleased] or {SKIP_FILE.name} ({line[:100]})')
    errors, warnings = style_problems(unreleased_section(since))
    for text in warnings:
        print(f'warning: {text}')
    for text in errors:
        print(f'style: {text}')
    if missing:
        print(f'\n{len(missing)} task id(s) shipped since {since} without a CHANGELOG entry. '
              f'Add one under [Unreleased], or list internal work in {SKIP_FILE.name}.')
    if missing or errors:
        return 1
    print(f'changelog coverage and style OK since {since} ({len(idless)} commit(s) without an id, '
          f'{len(warnings)} style warning(s))')
    return 0


if __name__ == '__main__':
    sys.exit(main())
