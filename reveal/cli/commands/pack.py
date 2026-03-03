"""reveal pack — token-budgeted context snapshot for LLM consumption."""

import argparse
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


# Entry point filename patterns (highest priority)
_ENTRY_POINT_PATTERNS = {
    'main.py', 'app.py', 'server.py', 'index.py', 'cli.py', 'run.py',
    'wsgi.py', 'asgi.py',
    'main.js', 'index.js', 'app.js', 'server.js',
    'main.ts', 'index.ts', 'app.ts',
    'main.go', 'main.rb', 'main.rs',
    'Makefile', 'Dockerfile', 'pyproject.toml', 'package.json', 'Cargo.toml',
}
# __init__.py excluded from unconditional entry points — most are near-empty;
# only promote them if they have substantial content (scored by size below)

_APPROX_CHARS_PER_TOKEN = 4


def create_pack_parser() -> argparse.ArgumentParser:
    """Create parser for reveal pack subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal pack',
        parents=[_build_global_options_parser()],
        description='Curate a token-budgeted context snapshot for LLM consumption.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal pack ./src                      # Default 2000-token budget\n"
            "  reveal pack ./src --budget 4000        # 4000-token budget\n"
            "  reveal pack ./src --budget 500-lines   # 500-line budget\n"
            "  reveal pack ./src --focus auth         # Emphasize auth module\n"
            "  reveal pack ./src --format json        # Structured output for tooling\n"
            "\n"
            "Prioritization order:\n"
            "  1. Entry points (main.py, index.js, etc.)\n"
            "  2. High-complexity files\n"
            "  3. Recently modified files\n"
            "  4. Other files (fills remaining budget)\n"
        )
    )
    parser.add_argument(
        'path',
        metavar='PATH',
        help='Directory or file to pack'
    )
    parser.add_argument(
        '--budget',
        metavar='N[=tokens|-lines]',
        default='2000',
        help='Token or line budget (e.g., 2000, 4000, 500-lines). Default: 2000 tokens'
    )
    parser.add_argument(
        '--focus',
        metavar='TOPIC',
        help='Emphasize files matching this name pattern (e.g., auth, api, models)'
    )
    return parser


def run_pack(args: Namespace) -> None:
    """Run the pack workflow."""
    path = Path(args.path)
    if not path.exists():
        print(f"Error: {args.path}: not found", file=sys.stderr)
        sys.exit(1)

    budget_tokens, budget_lines = _parse_budget(args.budget)
    focus = getattr(args, 'focus', None)

    # Collect candidate files
    candidates = _collect_candidates(path, focus)

    # Apply budget
    selected, meta = _apply_budget(candidates, budget_tokens, budget_lines, path)

    if args.format == 'json':
        print(json.dumps({
            'path': str(path),
            'budget': args.budget,
            'meta': meta,
            'files': selected
        }, indent=2, default=str))
        return

    _render_pack(path, selected, meta, args.verbose, budget_tokens, budget_lines)


def _parse_budget(budget_str: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse budget string into (tokens, lines)."""
    if budget_str.endswith('-lines'):
        try:
            return None, int(budget_str[:-6])
        except ValueError:
            pass
    try:
        return int(budget_str), None
    except ValueError:
        return 2000, None


def _collect_candidates(path: Path, focus: Optional[str]) -> List[Dict[str, Any]]:
    """Collect and score candidate files for the pack."""
    candidates = []

    for f in _walk_files(path):
        # Skip near-empty __init__.py files — they're almost always re-export
        # stubs and waste token budget without adding understanding
        if f.name == '__init__.py' and f.stat().st_size < 500:
            continue

        rel = f.relative_to(path)
        stat = f.stat()
        size_chars = stat.st_size
        tokens_approx = size_chars // _APPROX_CHARS_PER_TOKEN
        lines = _count_lines(f)

        priority = _compute_priority(f, rel, focus)

        candidates.append({
            'path': str(f),
            'relative': str(rel),
            'priority': priority,
            'tokens_approx': tokens_approx,
            'lines': lines,
            'mtime': stat.st_mtime,
            'size': stat.st_size,
        })

    # Sort: priority descending, then mtime descending
    candidates.sort(key=lambda c: (-c['priority'], -c['mtime']))
    return candidates


def _compute_priority(path: Path, rel: Path, focus: Optional[str]) -> float:
    """Score a file's priority for inclusion in the pack."""
    name = path.name.lower()
    rel_str = str(rel).lower()
    score = 0.0

    # Entry points: highest priority
    if name in _ENTRY_POINT_PATTERNS:
        score += 10.0

    # __init__.py: only gives a bonus if it has substantial content.
    # Near-empty ones (< 500 bytes) are already excluded by _collect_candidates.
    if name == '__init__.py' and path.stat().st_size > 2000:
        score += 2.0

    # Focus pattern match: high bonus
    if focus and focus.lower() in rel_str:
        score += 8.0

    # Key directories
    for keyword in ('main', 'core', 'api', 'routes', 'models', 'schema', 'auth', 'config'):
        if keyword in rel_str:
            score += 2.0

    # Penalize test/vendor/docs files
    for penalty in ('test_', '_test', '/tests/', '/vendor/', '/docs/', '/.', '__pycache__'):
        if penalty in rel_str:
            score -= 3.0

    # Penalize very large files (noisy)
    if path.stat().st_size > 50_000:
        score -= 1.0

    return max(score, 0.0)


def _apply_budget(
    candidates: List[Dict[str, Any]],
    budget_tokens: Optional[int],
    budget_lines: Optional[int],
    base_path: Path,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Select files within the budget."""
    selected = []
    used_tokens = 0
    used_lines = 0
    skipped = 0

    for c in candidates:
        if budget_tokens is not None:
            if used_tokens + c['tokens_approx'] > budget_tokens:
                skipped += 1
                continue
            used_tokens += c['tokens_approx']

        if budget_lines is not None:
            if used_lines + c['lines'] > budget_lines:
                skipped += 1
                continue
            used_lines += c['lines']

        selected.append(c)

    meta = {
        'total_candidates': len(candidates),
        'selected': len(selected),
        'skipped': skipped,
        'used_tokens_approx': used_tokens,
        'used_lines': used_lines,
        'budget_tokens': budget_tokens,
        'budget_lines': budget_lines,
    }
    return selected, meta


def _walk_files(path: Path) -> List[Path]:
    """Walk directory and return code/config files (respects common ignores)."""
    _SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                  '.mypy_cache', '.pytest_cache', 'dist', 'build', '.tox'}
    _CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.rb', '.go', '.rs', '.java',
        '.c', '.cpp', '.h', '.cs', '.php', '.swift', '.kt', '.scala',
        '.sh', '.bash', '.yaml', '.yml', '.toml', '.json', '.md',
        '.sql', '.html', '.css', '.scss',
    }
    _ROOT_FILES = {'Makefile', 'Dockerfile', 'pyproject.toml', 'package.json',
                   'Cargo.toml', 'go.mod', 'requirements.txt', 'setup.py'}

    results = []

    if path.is_file():
        return [path]

    for item in path.rglob('*'):
        if item.is_dir():
            continue
        # Skip hidden/ignored dirs
        if any(part.startswith('.') or part in _SKIP_DIRS for part in item.parts):
            continue
        # Include root config files
        if item.parent == path and item.name in _ROOT_FILES:
            results.append(item)
            continue
        # Include code files by extension
        if item.suffix.lower() in _CODE_EXTENSIONS:
            results.append(item)

    return results


def _count_lines(path: Path) -> int:
    """Count lines in a file."""
    try:
        return path.read_text(encoding='utf-8', errors='ignore').count('\n')
    except Exception:
        return 0


def _render_pack(
    path: Path,
    selected: List[Dict[str, Any]],
    meta: Dict[str, Any],
    verbose: bool,
    budget_tokens: Optional[int],
    budget_lines: Optional[int],
) -> None:
    """Render pack output as text."""
    budget_desc = (f"~{budget_tokens} tokens" if budget_tokens
                   else f"{budget_lines} lines")
    print(f"Pack: {path}  [{budget_desc} budget]")
    print(f"Selected {meta['selected']} of {meta['total_candidates']} files "
          f"(~{meta['used_tokens_approx']} tokens, {meta['used_lines']} lines)")
    print()

    if not selected:
        print("No files fit within budget.")
        return

    # Group by priority tier for display
    high = [f for f in selected if f['priority'] >= 8]
    medium = [f for f in selected if 2 <= f['priority'] < 8]
    low = [f for f in selected if f['priority'] < 2]

    if high:
        print("── Entry points / focus files ──")
        for f in high:
            _print_file_line(f, verbose)
        print()

    if medium:
        print("── Key modules ──")
        for f in medium:
            _print_file_line(f, verbose)
        print()

    if low:
        print("── Other files ──")
        for f in low:
            _print_file_line(f, verbose)
        print()

    if meta['skipped'] > 0:
        print(f"[{meta['skipped']} files excluded — exceeded budget]")


def _print_file_line(f: Dict[str, Any], verbose: bool) -> None:
    """Print one file entry."""
    rel = f['relative']
    tokens = f['tokens_approx']
    lines = f['lines']
    if verbose:
        print(f"  {rel:50} {tokens:5} tokens  {lines:4} lines")
    else:
        print(f"  {rel}")
