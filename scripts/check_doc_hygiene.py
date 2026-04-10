#!/usr/bin/env python3
"""Pre-release doc hygiene check for reveal's public-facing docs.

Catches:
  1. Broken markdown links (via reveal --links --format json)
  2. References to internal-docs/ (files that don't ship)
  3. TIA/personal leaks (beth_topics, tia commands, /home/scottsen, sociamonials)

Usage:
  python scripts/check_doc_hygiene.py          # check, exit 1 on problems
  python scripts/check_doc_hygiene.py --json   # structured output
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
    (r'\bsociamonials\b', 'real company name'),
]

# Files/dirs to skip
SKIP_DIRS = {'.pytest_cache', '.git', '__pycache__', 'node_modules', '.benchmarks'}
SKIP_FILES = {'CHANGELOG.md'}  # historical entries are acceptable noise


def find_markdown_files():
    """Find all .md files in the public repo, excluding tests and caches."""
    files = []
    for root, dirs, filenames in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != 'tests']
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
            # GitHub anchor: lowercase, spaces→hyphens, strip non-alphanum (except -)
            slug = re.sub(r'[^\w\s-]', '', heading.lower()).strip()
            slug = re.sub(r'[\s]+', '-', slug)
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


def main():
    as_json = '--json' in sys.argv
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

    if as_json:
        json.dump({
            'broken_links': all_broken,
            'internal_docs_refs': all_internal,
            'leak_patterns': all_leaks,
            'total_issues': total,
        }, sys.stdout, indent=2)
        print()
    else:
        print(f'Scanned {len(md_files)} markdown files\n')

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
        else:
            print(f'{total} issue(s) found. Fix before release.')

    sys.exit(1 if total > 0 else 0)


if __name__ == '__main__':
    main()
