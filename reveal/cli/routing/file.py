"""File and directory routing for reveal CLI.

Handles dispatching regular file paths and directories to the
appropriate handler, including guard checks, meta mode, and
directory tree/file-list views.
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

# Module-level imports so callers can mock reveal.cli.routing.file.handle_uri
# and reveal.cli.routing.file.handle_file in tests.
from .uri import handle_uri  # noqa: E402
from ...file_handler import handle_file  # noqa: E402


_NGINX_ADAPTER_FLAGS = {
    'check_acl': '--check-acl',
    'validate_nginx_acme': '--validate-nginx-acme',
    'check_conflicts': '--check-conflicts',
    'cpanel_certs': '--cpanel-certs',
    'diagnose': '--diagnose',
    'global_audit': '--global-audit',
}
_SSL_ADAPTER_FLAGS = {
    'expiring_within': '--expiring-within',
    'summary': '--summary',
    'validate_nginx': '--validate-nginx',
}
_NGINX_EXTENSIONS = {'.conf', '.ini', ''}  # '' = files with no extension (e.g. nginx, site.conf)
_MARKDOWN_EXTENSIONS = {'.md', '.markdown', '.rst', '.txt', ''}


def _parse_file_line_syntax(path_str: str) -> tuple[Path, Optional[str]]:
    """Parse file:line or file:line-line syntax.

    Args:
        path_str: Path string potentially with :line suffix

    Returns:
        Tuple of (Path, element_from_path)
    """
    path = Path(path_str)
    element_from_path = None

    # Support file:line and file:line-line syntax (e.g., app.py:50, app.py:50-60)
    if not path.exists() and ':' in path_str:
        match = re.match(r'^(.+?):(\d+(?:-\d+)?)$', path_str)
        if match:
            potential_path = Path(match.group(1))
            if potential_path.exists():
                path = potential_path
                element_from_path = f":{match.group(2)}"

    return path, element_from_path


def _validate_path_exists(path: Path, path_str: str) -> None:
    """Validate that path exists, providing helpful error messages."""
    if not path.exists():
        cwd = os.getcwd()
        if ':' in path_str and re.search(r':\d+', path_str):
            base_path = path_str.rsplit(':', 1)[0]
            print(f"Error: {path_str} not found", file=sys.stderr)
            print(f"Hint: If extracting lines, use: reveal {base_path} :{path_str.rsplit(':', 1)[1]}", file=sys.stderr)
        else:
            abs_suggestion = os.path.join(cwd, path_str)
            print(f"Error: {path_str} not found", file=sys.stderr)
            print(f"Hint: Running from {cwd}", file=sys.stderr)
            print(f"      Try: reveal {abs_suggestion}", file=sys.stderr)
        sys.exit(1)


def _stat_one_file(fpath: Path, ext_counts: dict) -> Optional[tuple]:
    """Stat a single file and update ext_counts. Returns (size, mtime) or None."""
    try:
        stat = fpath.stat()
    except OSError:
        return None
    ext_counts[fpath.suffix.lower().lstrip('.') or '(no ext)'] += 1
    return stat.st_size, stat.st_mtime


def _collect_dir_stats(path: Path) -> tuple:
    """Walk a directory and collect file count, size, mtime, extension counts.

    Returns:
        (ext_counts, total_files, total_size, newest_mtime, oldest_mtime)
    """
    from collections import defaultdict
    ext_counts: dict = defaultdict(int)
    total_files = 0
    total_size = 0
    newest_mtime = 0.0
    oldest_mtime = float('inf')
    for root, _dirs, files in os.walk(path):
        for fname in files:
            result = _stat_one_file(Path(root) / fname, ext_counts)
            if result is None:
                continue
            size, mtime = result
            total_files += 1
            total_size += size
            newest_mtime = max(newest_mtime, mtime)
            oldest_mtime = min(oldest_mtime, mtime)
    return ext_counts, total_files, total_size, newest_mtime, oldest_mtime


def _render_dir_meta_text(meta: dict) -> None:
    """Print directory metadata in human-readable text format."""
    print(f"Directory: {meta['name']}\n")
    print(f"Path:       {meta['path']}")
    print(f"Files:      {meta['total_files']:,}")
    print(f"Size:       {meta['size_human']}")
    if meta['modified']:
        print(f"Modified:   {meta['modified']}")
    if meta['oldest_file']:
        print(f"Oldest:     {meta['oldest_file']}")
    if meta['by_extension']:
        print(f"\nBy extension:")
        for ext, count in meta['by_extension'].items():
            print(f"  .{ext:<12} {count:>6,}")


def _show_directory_meta(path: Path, args: 'Namespace') -> None:
    """Show metadata summary for a directory.

    Args:
        path: Directory path
        args: Parsed arguments (uses args.format for JSON output)
    """
    import datetime
    from ...utils import safe_json_dumps, format_size

    ext_counts, total_files, total_size, newest_mtime, oldest_mtime = _collect_dir_stats(path)
    meta = {
        'path': str(path), 'name': path.name,
        'total_files': total_files, 'total_size': total_size,
        'size_human': format_size(total_size),
        'modified': datetime.datetime.fromtimestamp(newest_mtime).isoformat(timespec='seconds') if newest_mtime else None,
        'oldest_file': datetime.datetime.fromtimestamp(oldest_mtime).isoformat(timespec='seconds') if oldest_mtime != float('inf') else None,
        'by_extension': dict(sorted(ext_counts.items(), key=lambda x: -x[1])),
    }
    output_format = getattr(args, 'format', 'text')
    if output_format == 'json':
        print(safe_json_dumps(meta))
    else:
        _render_dir_meta_text(meta)


def _parse_ext_arg(ext_arg: Optional[str]) -> Optional[list]:
    """Parse --ext argument into a list of normalized extensions.

    Args:
        ext_arg: Raw --ext value (e.g., 'md', 'py,md', '.py,.md')

    Returns:
        List of lowercase extensions without dots, or None if not specified
    """
    if not ext_arg:
        return None
    return [e.strip().lower().lstrip('.') for e in ext_arg.split(',') if e.strip()]


def _build_ast_query_from_flags(path: Path, args: 'Namespace') -> str:
    """Build AST query URI from convenience flags."""
    query_params = []
    if getattr(args, 'search', None):
        query_params.append(f"name~={args.search}")
    if getattr(args, 'type', None):
        query_params.append(f"type={args.type}")
    if getattr(args, 'sort', None):
        sort_field = args.sort
        if getattr(args, 'desc', False) and not sort_field.startswith('-'):
            sort_field = f"-{sort_field}"
        query_params.append(f"sort={sort_field}")

    query_string = '&'.join(query_params)
    return f"ast://{path}?{query_string}"


def _guard_hotspots_flag(args: 'Namespace', path_str: str) -> None:
    if not getattr(args, 'hotspots', False):
        return
    print("❌ Error: --hotspots only works with stats:// adapter", file=sys.stderr)
    print(file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print(f"  reveal stats://{path_str}?hotspots=true    # URI param (preferred)", file=sys.stderr)
    print(f"  reveal stats://{path_str} --hotspots        # Flag (legacy)", file=sys.stderr)
    print(file=sys.stderr)
    print("Learn more: reveal help://stats", file=sys.stderr)
    sys.exit(1)


def _guard_nginx_flags(args: 'Namespace', path_str: str) -> None:
    """Exit with error if nginx-specific flags are used on non-nginx file extensions."""
    path_ext = Path(path_str).suffix.lower() if '.' in Path(path_str).name else ''
    if path_ext in _NGINX_EXTENSIONS:
        return
    for attr, flag in _NGINX_ADAPTER_FLAGS.items():
        if getattr(args, attr, False):
            print(f"❌ Error: {flag} only works with nginx config files", file=sys.stderr)
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print(f"  reveal nginx.conf {flag}                    # with a .conf file", file=sys.stderr)
            print(f"  reveal nginx://nginx.conf?{attr.replace('_', '-')}=true  # URI param", file=sys.stderr)
            print(file=sys.stderr)
            print("Learn more: reveal help://nginx", file=sys.stderr)
            sys.exit(1)


_SSL_FLAG_EXAMPLES = {
    'expiring_within': (
        "  reveal ssl://example.com --expiring-within 30   # single domain (CLI flag)\n"
        "  reveal 'ssl://example.com?expiring-within=30' --check  # URI param form (preferred for pipelines)\n"
        "  reveal ssl://nginx:///etc/nginx --check --expiring-within 30  # batch"
    ),
    'summary': (
        "  reveal ssl://nginx:///etc/nginx --check --summary   # batch summary counts\n"
        "  reveal ssl://example.com --check                    # single domain check"
    ),
    'validate_nginx': (
        "  reveal ssl://example.com --validate-nginx   # cross-validate cert vs nginx config"
    ),
}


def _guard_ssl_flags(args: 'Namespace') -> None:
    """Exit with error if ssl:// adapter flags are used on plain file paths."""
    for attr, flag in _SSL_ADAPTER_FLAGS.items():
        if getattr(args, attr, False):
            print(f"❌ Error: {flag} only works with the ssl:// adapter", file=sys.stderr)
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print(_SSL_FLAG_EXAMPLES[attr], file=sys.stderr)
            print(file=sys.stderr)
            print("Learn more: reveal help://ssl", file=sys.stderr)
            sys.exit(1)


def _guard_related_flags(args: 'Namespace', path_str: str) -> None:
    """Exit with error if --related/--related-all are used on non-markdown files."""
    if not (getattr(args, 'related', False) or getattr(args, 'related_all', False)):
        return
    md_ext = Path(path_str).suffix.lower() if '.' in Path(path_str).name else ''
    if md_ext in _MARKDOWN_EXTENSIONS:
        return
    flag = '--related-all' if getattr(args, 'related_all', False) else '--related'
    print(f"❌ Error: {flag} only works with markdown files", file=sys.stderr)
    print(file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print(f"  reveal docs/ --related          # on a markdown directory", file=sys.stderr)
    print(f"  reveal doc.md --related         # on a .md file", file=sys.stderr)
    print(file=sys.stderr)
    print("Learn more: reveal help://markdown", file=sys.stderr)
    sys.exit(1)


def _handle_directory_path(path: Path, args: 'Namespace') -> None:
    """Route a resolved directory path to directory-meta, file-list, or tree view."""
    from ...tree_view import show_directory_tree, show_file_list
    if getattr(args, 'meta', False):
        _show_directory_meta(path, args)
        return
    sort_by = getattr(args, 'sort', None)
    include_extensions = _parse_ext_arg(getattr(args, 'ext', None))
    if getattr(args, 'files', False):
        # --files defaults to newest-first; --asc flips it
        sort_desc = not getattr(args, 'asc', False)
        print(show_file_list(str(path),
                             respect_gitignore=args.respect_gitignore,
                             exclude_patterns=args.exclude,
                             sort_by=sort_by, sort_desc=sort_desc,
                             include_extensions=include_extensions))
    else:
        sort_desc = getattr(args, 'desc', False)
        print(show_directory_tree(str(path), depth=args.depth,
                                  max_entries=args.max_entries, fast=args.fast,
                                  respect_gitignore=args.respect_gitignore,
                                  exclude_patterns=args.exclude,
                                  dir_limit=getattr(args, 'dir_limit', 0),
                                  sort_by=sort_by, sort_desc=sort_desc,
                                  include_extensions=include_extensions))


def _handle_file_path(path: Path, element_from_path: Optional[str], args: 'Namespace') -> None:
    """Route a resolved file path — to ast query if convenience flags set, else normal handler."""
    if getattr(args, 'search', None) or getattr(args, 'sort', None) or getattr(args, 'type', None):
        handle_uri(_build_ast_query_from_flags(path, args), args.element, args)
        return

    element = element_from_path or args.element
    if not element and getattr(args, 'section', None):
        if path.suffix.lower() in ('.md', '.markdown'):
            element = args.section
        else:
            print("❌ Error: --section only works with markdown files (.md, .markdown)", file=sys.stderr)
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print(f"  reveal {path}.md --section 'Heading Name'   # markdown section extraction", file=sys.stderr)
            print(f"  reveal {path} \"element_name\"                # for non-markdown, use element syntax", file=sys.stderr)
            print(file=sys.stderr)
            print("Learn more: reveal help://ux", file=sys.stderr)
            sys.exit(1)
    handle_file(str(path), element, args.meta, args.format, args)


def handle_file_or_directory(path_str: str, args: 'Namespace') -> None:
    """Handle regular file or directory path.

    Args:
        path_str: Path string to file or directory
        args: Parsed arguments
    """
    if getattr(args, 'check', False):
        from ...cli.commands.check import run_check
        run_check(args)
        return

    _guard_hotspots_flag(args, path_str)
    _guard_nginx_flags(args, path_str)
    _guard_ssl_flags(args)
    _guard_related_flags(args, path_str)

    path, element_from_path = _parse_file_line_syntax(path_str)
    _validate_path_exists(path, path_str)

    if path.is_dir():
        _handle_directory_path(path, args)
    elif path.is_file():
        _handle_file_path(path, element_from_path, args)
    else:
        print(f"Error: {path_str} is neither file nor directory", file=sys.stderr)
        sys.exit(1)
