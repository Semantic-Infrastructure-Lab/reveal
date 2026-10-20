#!/usr/bin/env python3
"""Pre-release doc hygiene check for reveal's public-facing docs.

Catches:
  1. Broken markdown links (via reveal --links --format json)
  2. References to internal-docs/ (files that don't ship)
  3. TIA/personal leaks (beth_topics, tia commands, /home/scottsen)
  4. Private names (clients, partners, people) in ANY tracked file -- code, tests,
     fixtures, CHANGELOG included. The term list comes from the environment, never
     from this repo. Not covered by --baseline: one hit fails the run.

Usage:
  python scripts/check_doc_hygiene.py                       # check, exit 1 on any problem
  python scripts/check_doc_hygiene.py --json                # structured output
  python scripts/check_doc_hygiene.py --baseline FILE       # ratchet: exit 1 only if
                                                              # total_issues > FILE's count
                                                              # (mirrors .github/b006_baseline.txt)
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Patterns that should not appear in public docs
LEAK_PATTERNS = [
    (r'\btia[-_ ](?:search|session|project|beth|boot|save)\b', 'TIA CLI command'),
    (r'/home/scottsen/', 'hardcoded developer path'),
    (r'~/src/tia/', 'hardcoded TIA path'),
]

# Names that must never appear anywhere in the public repo come from outside it, so this
# public file never spells them: REVEAL_PRIVATE_TERMS (newline- or comma-separated; CI
# passes a repository secret) or REVEAL_PRIVATE_TERMS_FILE (one term per line, '#'
# comments). Case-insensitive substring match. Neither set: the check is skipped and says so.
def _private_terms():
    raw = os.environ.get('REVEAL_PRIVATE_TERMS', '')
    path = os.environ.get('REVEAL_PRIVATE_TERMS_FILE')
    if path:
        raw += '\n' + Path(path).read_text(encoding='utf-8')
    terms = [t.strip().lower() for t in re.split(r'[\n,]', raw)]
    return [t for t in terms if t and not t.startswith('#')] or None

# Files/dirs to skip
SKIP_DIRS = {'.pytest_cache', '.git', '__pycache__', 'node_modules', '.benchmarks', 'build', 'dist'}
SKIP_FILES = {'CHANGELOG.md'}  # historical entries are acceptable noise


def find_markdown_files():
    """Find all .md files in the public repo, excluding tests and caches."""
    files = []
    for root, dirs, filenames in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != 'tests' and not d.endswith('.egg-info')]
        for f in filenames:
            if f.endswith('.md'):
                files.append(Path(root) / f)
    return sorted(files)


def _anchor_exists(md_path, anchor):
    """Check if a markdown heading anchor exists in the target file."""
    try:
        text = md_path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False
    # Convert headings to GitHub-style anchors for comparison
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('#'):
            heading = line.lstrip('#').strip()
            # GitHub anchor: lowercase, strip non-alphanum (except -), then each space is its own
            # hyphen: "a — b" is a--b, not a-b (BACK-2066)
            slug = re.sub(r'[^\w\s-]', '', heading.lower()).strip()
            slug = re.sub(r'\s', '-', slug)
            if slug == anchor:
                return True
    return False


def check_broken_links(md_file):
    """Use reveal to extract links and find broken ones."""
    broken = []
    try:
        result = subprocess.run(
            ['reveal', str(md_file), '--links', '--format', 'json'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return broken

        data = json.loads(result.stdout)
        for link in data.get('structure', {}).get('links', []):
            if link.get('broken'):
                url = link.get('url', '')
                # Cross-file anchor: reveal may flag these as broken if it
                # doesn't verify anchors. Check manually.
                if '#' in url:
                    file_part, anchor = url.rsplit('#', 1)
                    if file_part:
                        target = (md_file.parent / file_part).resolve()
                        if target.exists() and _anchor_exists(target, anchor):
                            continue  # file + anchor both valid
                broken.append({
                    'file': str(md_file.relative_to(PROJECT_ROOT)),
                    'line': link.get('line', '?'),
                    'text': link.get('text', ''),
                    'url': url,
                })
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        pass
    return broken


def check_internal_docs_refs(md_file):
    """Find prose references to internal-docs/ (not just links)."""
    hits = []
    try:
        text = md_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return hits

    rel = str(md_file.relative_to(PROJECT_ROOT))
    for i, line in enumerate(text.split('\n'), 1):
        if 'internal-docs' in line.lower():
            hits.append({
                'file': rel,
                'line': i,
                'content': line.strip()[:120],
            })
    return hits


def check_leak_patterns(md_file):
    """Find TIA/personal leaks in prose, frontmatter, and examples."""
    hits = []
    try:
        text = md_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return hits

    rel = str(md_file.relative_to(PROJECT_ROOT))
    for i, line in enumerate(text.split('\n'), 1):
        for pattern, label in LEAK_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                hits.append({
                    'file': rel,
                    'line': i,
                    'pattern': label,
                    'content': line.strip()[:120],
                })
                break  # one hit per line is enough
    return hits


def _tracked_files():
    """Every file git tracks in the public repo (all types, tests and CHANGELOG included)."""
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=PROJECT_ROOT, capture_output=True,
                         check=True)
    return [PROJECT_ROOT / p for p in out.stdout.decode('utf-8').split('\0') if p]


def check_private_names(files, terms):
    """Find any private term in any file. A hit reports file and line only: printing the
    line would put the term into public CI logs."""
    hits = []
    for path in files:
        try:
            text = path.read_bytes().decode('utf-8').lower()
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable
        if not any(t in text for t in terms):
            continue
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        for i, line in enumerate(text.split('\n'), 1):
            if any(t in line for t in terms):
                hits.append({'file': rel, 'line': i})
    return hits


def _read_baseline(path: str) -> int:
    try:
        return int(Path(path).read_text(encoding='utf-8').strip())
    except (OSError, ValueError) as e:
        print(f"Error: couldn't read baseline count from {path}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    as_json = '--json' in sys.argv
    baseline = None
    if '--baseline' in sys.argv:
        idx = sys.argv.index('--baseline')
        try:
            baseline_path = sys.argv[idx + 1]
        except IndexError:
            print("Error: --baseline requires a file path", file=sys.stderr)
            sys.exit(1)
        baseline = _read_baseline(baseline_path)

    md_files = find_markdown_files()

    all_broken = []
    all_internal = []
    all_leaks = []

    for f in md_files:
        all_broken.extend(check_broken_links(f))
        if f.name not in SKIP_FILES:
            all_internal.extend(check_internal_docs_refs(f))
        if f.name not in SKIP_FILES:
            all_leaks.extend(check_leak_patterns(f))

    total = len(all_broken) + len(all_internal) + len(all_leaks)
    terms = _private_terms()
    private = check_private_names(_tracked_files(), terms) if terms else []

    if as_json:
        json.dump({
            'broken_links': all_broken,
            'internal_docs_refs': all_internal,
            'leak_patterns': all_leaks,
            'private_names_checked': terms is not None,
            'private_names': private,
            'total_issues': total,
        }, sys.stdout, indent=2)
        print()
    else:
        print(f'Scanned {len(md_files)} markdown files\n')

        if terms is None:
            print('Private-name check skipped: set REVEAL_PRIVATE_TERMS or REVEAL_PRIVATE_TERMS_FILE.\n')
        elif private:
            print(f'=== PRIVATE NAMES ({len(private)}) -- never allowed, not baselined ===')
            for p in private:
                print(f"  ! {p['file']}:{p['line']}")
            print()

        if all_broken:
            print(f'=== BROKEN LINKS ({len(all_broken)}) ===')
            for b in all_broken:
                print(f"  X {b['file']}:{b['line']}  [{b['text']}]({b['url']})")
            print()

        if all_internal:
            print(f'=== INTERNAL-DOCS REFERENCES ({len(all_internal)}) ===')
            for i in all_internal:
                print(f"  ! {i['file']}:{i['line']}  {i['content']}")
            print()

        if all_leaks:
            print(f'=== TIA/PERSONAL LEAKS ({len(all_leaks)}) ===')
            for l in all_leaks:
                print(f"  ~ {l['file']}:{l['line']}  ({l['pattern']})  {l['content']}")
            print()

        if total == 0:
            print('All clear — no doc hygiene issues found.')
        elif baseline is not None:
            print(f'{total} issue(s) found (baseline: {baseline}).')
        else:
            print(f'{total} issue(s) found. Fix before release.')

    if private:
        print(f"\n❌ {len(private)} private name(s) in the public repo -- use a generic term.",
              file=sys.stderr)
        sys.exit(1)

    if baseline is None:
        sys.exit(1 if total > 0 else 0)

    # Ratchet mode (mirrors .github/b006_baseline.txt): only a regression above
    # the tracked baseline fails release prep. The baseline itself is known,
    # pre-existing debt (mostly VALIDATION.md links into internal-docs/, which
    # was intentionally moved out of the public repo) that isn't being cleared
    # in a single pass — a permanently-red check gets ignored, a ratchet doesn't.
    if total > baseline:
        print(f"\n❌ Doc hygiene issue count increased ({baseline} -> {total}) — "
              f"a new broken link/internal-docs leak was introduced.", file=sys.stderr)
        sys.exit(1)
    elif total < baseline:
        print(f"\n✅ Doc hygiene count decreased ({baseline} -> {total}) — "
              f"update the baseline file to {total} to lock in the improvement.")
    sys.exit(0)


if __name__ == '__main__':
    main()
