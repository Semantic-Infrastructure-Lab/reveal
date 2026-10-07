"""File and directory routing for reveal CLI.

Handles dispatching regular file paths and directories to the
appropriate handler, including guard checks, meta mode, and
directory tree/file-list views.
"""

import os
import re
import shlex
import sys
from pathlib import Path
from argparse import Namespace
from contextlib import nullcontext
from typing import Optional

# Module-level imports so callers can mock reveal.cli.routing.file.handle_uri
# and reveal.cli.routing.file.handle_file in tests.
from .uri import handle_uri  # noqa: E402
from .formats import (  # noqa: E402
    DEFAULT_OUTPUT_FORMATS, reject_unhonored_also_json, require_supported_format,
)
from ...file_handler import handle_file  # noqa: E402
from .grep import handle_grep, handle_grep_directory
from .ledger import FlagLedger, ledger_of, mark, peek  # noqa: E402
from ...utils.path_utils import to_posix  # noqa: E402
from ...registry import get_markdown_extensions  # noqa: E402


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
            if abs_suggestion != path_str and os.path.exists(abs_suggestion):
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


def _collect_dir_stats(
    path: Path, respect_gitignore: bool = True, exclude_patterns: Optional[list] = None,
) -> tuple:
    """Walk a directory and collect file count, size, mtime, extension counts.

    BACK-1362: this used to walk raw os.walk() with no filtering at all -- .git
    internals, node_modules, and gitignored files were all silently counted. It is the
    display walk (BACK-1581): --meta counts exactly what the tree and --files list.

    Returns:
        (ext_counts, total_files, total_size, newest_mtime, oldest_mtime)
    """
    from collections import defaultdict
    from ...utils.path_utils import DISPLAY, _walk_code_files
    ext_counts: dict = defaultdict(int)
    total_files = 0
    total_size = 0
    newest_mtime = 0.0
    oldest_mtime = float('inf')
    for fpath in _walk_code_files(path, exclude_patterns, respect_gitignore, purpose=DISPLAY):
        result = _stat_one_file(fpath, ext_counts)
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

    ext_counts, total_files, total_size, newest_mtime, oldest_mtime = _collect_dir_stats(
        path, respect_gitignore=getattr(args, 'respect_gitignore', True),
        exclude_patterns=getattr(args, 'exclude', None))
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
    if getattr(args, 'name', None):
        query_params.append(f"name~={args.name}")
    if getattr(args, 'type', None):
        query_params.append(f"type={args.type}")
    if getattr(args, 'sort', None):
        sort_field = args.sort
        if getattr(args, 'desc', False) and not sort_field.startswith('-'):
            sort_field = f"-{sort_field}"
        query_params.append(f"sort={sort_field}")

    query_string = '&'.join(query_params)
    return f"ast://{to_posix(path)}?{query_string}"


def _guard_hotspots_flag(args: 'Namespace', path_str: str) -> None:
    if not getattr(args, 'hotspots', False):
        return
    print("❌ Error: --hotspots only works with stats:// adapter", file=sys.stderr)
    print(file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print(f"  reveal 'stats://{path_str}?hotspots=true'  # URI param (preferred)", file=sys.stderr)
    print(f"  reveal stats://{path_str} --hotspots        # Flag (legacy)", file=sys.stderr)
    print(file=sys.stderr)
    print("Learn more: reveal help://stats", file=sys.stderr)
    sys.exit(1)


def _guard_adapter_flags(args: 'Namespace', scheme: str, path_str: Optional[str]) -> None:
    """Exit with error if an adapter's CLI flags are used on a plain file path.

    The flag ownership lives on the adapter (GUARDED_FLAGS / GUARDED_FLAG_*),
    not in this router — see reveal/adapters/base.py. When path_str is given and
    its extension is one the adapter accepts, the guard is skipped.
    """
    from ...adapters.registry import get_adapter_class
    adapter_cls = get_adapter_class(scheme)
    if adapter_cls is None or not getattr(adapter_cls, 'GUARDED_FLAGS', ()):
        return
    if path_str is not None:
        path_ext = Path(path_str).suffix.lower() if '.' in Path(path_str).name else ''
        if path_ext in getattr(adapter_cls, 'GUARDED_FLAG_EXTENSIONS', frozenset()):
            return
    context = getattr(adapter_cls, 'GUARDED_FLAG_CONTEXT', scheme)
    help_topic = getattr(adapter_cls, 'GUARDED_FLAG_HELP', scheme)
    for spec in adapter_cls.GUARDED_FLAGS:
        if getattr(args, spec.attr, False):
            print(f"❌ Error: {spec.flag} only works with {context}", file=sys.stderr)
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print(spec.examples, file=sys.stderr)
            print(file=sys.stderr)
            print(f"Learn more: reveal help://{help_topic}", file=sys.stderr)
            sys.exit(1)


def _guard_nginx_flags(args: 'Namespace', path_str: str) -> None:
    """Exit with error if nginx-specific flags are used on non-nginx file extensions."""
    _guard_adapter_flags(args, 'nginx', path_str)


def _guard_ssl_flags(args: 'Namespace') -> None:
    """Exit with error if ssl:// adapter flags are used on plain file paths."""
    _guard_adapter_flags(args, 'ssl', None)


def _guard_cpanel_flags(args: 'Namespace') -> None:
    """Exit with error if cpanel:// adapter flags are used on plain file paths."""
    _guard_adapter_flags(args, 'cpanel', None)


def _guard_letsencrypt_flags(args: 'Namespace') -> None:
    """Exit with error if letsencrypt:// adapter flags are used on plain file paths."""
    _guard_adapter_flags(args, 'letsencrypt', None)


def _guard_autossl_flags(args: 'Namespace') -> None:
    """Exit with error if autossl:// adapter flags are used on plain file paths."""
    _guard_adapter_flags(args, 'autossl', None)


def _guard_related_flags(args: 'Namespace', path_str: str) -> None:
    """Exit with error if --related/--related-all are used on non-markdown files."""
    if not (getattr(args, 'related', False) or getattr(args, 'related_all', False)):
        return
    md_ext = Path(path_str).suffix.lower() if '.' in Path(path_str).name else ''
    if md_ext in get_markdown_extensions():
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
    from ...tree_view import (
        show_directory_tree, show_file_list, show_directory_tree_json, show_file_list_json,
    )
    if getattr(args, 'meta', False):
        _show_directory_meta(path, args)
        return
    # A search's hit list is a flat result list: --max-items caps it (BACK-1633), so the
    # directory-listing note below is not for --grep, and --ext keeps the files the
    # listing would (it was dropped, and every file type was searched).
    if getattr(args, 'grep', None):
        if getattr(args, 'name', None):
            print("Note: --name ignored when --grep is used (--grep searches all text, --name filters structural output)", file=sys.stderr)
        reject_unhonored_also_json(args, '--grep')
        handle_grep_directory(to_posix(path), args.grep, args, _parse_ext_arg(getattr(args, 'ext', None)))
        return
    # BACK-1203: --max-items/--max-snippet-chars have no analog on a bare
    # directory listing (a recursive tree, not a flat result list) — the
    # equivalent flag here is --max-entries. Hint instead of silently
    # ignoring, matching BACK-1202's "honest not-applicable" precedent.
    if getattr(args, 'max_items', None) is not None or getattr(args, 'max_snippet_chars', None) is not None:
        print(
            "Note: --max-items/--max-snippet-chars have no effect on a directory listing "
            "(use --max-entries to bound the number of entries shown)",
            file=sys.stderr,
        )
    # --type on a directory without --name can mean two different things:
    #   1. File-type filter (--type markdown, --type python) — user wants to
    #      filter the directory listing to files of that language/format.
    #   2. AST node-type filter (--type class, --type function) — user wants to
    #      search for AST nodes of that type across the directory.
    # Distinguish by checking against known file-type names. If the value
    # matches a known file type, translate to extensions and fall through to
    # the directory display. Otherwise, route to the AST handler as before.
    _TYPE_TO_EXT = {
        'python': 'py', 'py': 'py',
        'markdown': 'md,markdown', 'md': 'md,markdown',
        'yaml': 'yaml,yml', 'yml': 'yaml,yml',
        'json': 'json', 'toml': 'toml', 'ini': 'ini', 'cfg': 'cfg',
        'sql': 'sql', 'sh': 'sh', 'bash': 'sh',
        'typescript': 'ts,tsx', 'ts': 'ts,tsx',
        'javascript': 'js,jsx', 'js': 'js,jsx',
        'html': 'html,htm', 'css': 'css',
        'rust': 'rs', 'go': 'go', 'java': 'java', 'kotlin': 'kt',
        'ruby': 'rb', 'php': 'php',
    }
    type_from_args = getattr(args, 'type', None)
    ext_from_args = getattr(args, 'ext', None)
    if type_from_args and not getattr(args, 'name', None):
        mapped = _TYPE_TO_EXT.get(type_from_args.lower())
        if mapped and not ext_from_args:
            ext_from_args = mapped  # treat as file-type filter; fall through
        else:
            # AST node-type filter (class, function, etc.) or --ext already set
            handle_uri(_build_ast_query_from_flags(path, args), args.element, args)
            return
    elif getattr(args, 'name', None):
        handle_uri(_build_ast_query_from_flags(path, args), args.element, args)
        return
    require_supported_format(args, DEFAULT_OUTPUT_FORMATS, 'a directory listing')
    reject_unhonored_also_json(args, 'a directory listing')
    sort_by = getattr(args, 'sort', None)
    include_extensions = _parse_ext_arg(ext_from_args)
    output_format = getattr(args, 'format', 'text')
    if getattr(args, 'files', False):
        # --files defaults to newest-first; --asc flips it
        sort_desc = not getattr(args, 'asc', False)
        if output_format == 'json':
            from ...utils import safe_json_dumps
            print(safe_json_dumps(show_file_list_json(
                str(path), respect_gitignore=args.respect_gitignore,
                exclude_patterns=args.exclude,
                sort_by=sort_by, sort_desc=sort_desc,
                include_extensions=include_extensions,
                max_entries=args.max_entries)))
        else:
            print(show_file_list(str(path),
                                 respect_gitignore=args.respect_gitignore,
                                 exclude_patterns=args.exclude,
                                 sort_by=sort_by, sort_desc=sort_desc,
                                 include_extensions=include_extensions,
                                 max_entries=args.max_entries))
    else:
        sort_desc = getattr(args, 'desc', False)
        if output_format == 'json':
            from ...utils import safe_json_dumps
            print(safe_json_dumps(show_directory_tree_json(
                str(path), depth=args.depth if args.depth is not None else 3,
                max_entries=args.max_entries, fast=args.fast,
                respect_gitignore=args.respect_gitignore,
                exclude_patterns=args.exclude,
                dir_limit=getattr(args, 'dir_limit', 0),
                sort_by=sort_by, sort_desc=sort_desc,
                include_extensions=include_extensions)))
        else:
            print(show_directory_tree(str(path), depth=args.depth if args.depth is not None else 3,
                                      max_entries=args.max_entries, fast=args.fast,
                                      respect_gitignore=args.respect_gitignore,
                                      exclude_patterns=args.exclude,
                                      dir_limit=getattr(args, 'dir_limit', 0),
                                      sort_by=sort_by, sort_desc=sort_desc,
                                      include_extensions=include_extensions))


# Flags whose answer never reads the ELEMENT argument (dest -> spelling). `reveal a b --flag`
# parses b as the element, so these answered for a alone and exited 0 (BACK-1687, BACK-1715).
# A new flag of this kind is declared here, not guarded with another `if`. An early-exit mode
# in main._SPECIAL_MODES that reads the path is checked against this set by
# tests/test_element_less_completeness_back1735.py; the other flags are declared by hand.
ELEMENT_LESS_FLAGS = {
    'validate_schema': '--validate-schema', 'check': '--check', 'meta': '--meta',
    'extract': '--extract', 'check_acl': '--check-acl', 'validate_nginx_acme': '--validate-nginx-acme',
    'global_audit': '--global-audit', 'check_conflicts': '--check-conflicts',
    'cpanel_certs': '--cpanel-certs', 'diagnose': '--diagnose',
    'explain_file': '--explain-file', 'capabilities': '--capabilities', 'show_ast': '--show-ast',
    'decorator_stats': '--decorator-stats',
}

# Flags that ARE the element, spelled as a flag (dest -> spelling). Beside an element argument
# one of the two was dropped: `reveal a.md b.md --section X` looked for 'b.md' in a.md and never
# mentioned X, and `reveal a.md A --section X` extracted A and exited 0 (BACK-1728).
ELEMENT_FLAGS = {'section': '--section'}

# Early-exit modes that read no path at all (dest -> spelling): `reveal a.py b.py --rules` listed
# the rules, dropped both paths and exited 0 (BACK-1751). Every main._SPECIAL_MODES entry is
# declared either here or, when its handler reads the path, in ELEMENT_LESS_FLAGS;
# tests/test_element_less_completeness_back1735.py checks that against the handlers.
PATHLESS_FLAGS = {
    'list_supported': '--list-supported', 'languages': '--languages', 'adapters': '--adapters',
    'language_info': '--language-info', 'agent_help': '--agent-help', 'rules': '--rules',
    'profiles': '--profiles', 'schema': '--schema', 'explain': '--explain',
    'list_schemas': '--list-schemas', 'discover': '--discover', 'stdin': '--stdin',
    'disable_breadcrumbs': '--disable-breadcrumbs',
}


def reject_ignored_element(args: 'Namespace') -> None:
    """Exit 2 when an element-less or element flag is given an element (a second path or ``file:N``).

    One disclosed refusal in place of a run that silently covers the first path only, or drops
    the flag's own element. URIs and ``@file`` lists read their second argument themselves and
    are left alone.
    """
    declared = [(dest, spelling) for dest, spelling in {**ELEMENT_LESS_FLAGS, **ELEMENT_FLAGS}.items()
                if getattr(args, dest, None)]
    path_str = getattr(args, 'path', None)
    if not declared or not path_str or '://' in path_str or path_str.startswith('@'):
        return
    element = getattr(args, 'element', None) or _parse_file_line_syntax(path_str)[1]
    if not element:
        return
    dest, spelling = declared[0]
    if dest in ELEMENT_FLAGS:
        print(f"Error: {spelling} '{getattr(args, dest)}' and the element '{element}' both name what to "
              f"extract; one would be ignored.\nGive one of them: reveal reads one file and one element per call.",
              file=sys.stderr)
    else:
        print(f"Error: {spelling} reads no element and covers one path per call; '{element}' would be ignored.\n"
              f"Run it once per path, or for several: ls PATHS | reveal --stdin {_flag_usage(dest, spelling)}",
              file=sys.stderr)
    sys.exit(2)


def reject_ignored_path(args: 'Namespace', dest: str) -> None:
    """Exit 2 when the special mode ``dest`` reads no path but was given one (or a URI, ``@file``).

    Called with the mode that is about to run, so a path-reading mode dispatched first keeps it.
    """
    spelling = PATHLESS_FLAGS.get(dest)
    ignored = [f"'{value}'" for value in (getattr(args, 'path', None), getattr(args, 'element', None))
               if isinstance(value, str) and value]
    if not spelling or not ignored:
        return
    value = getattr(args, dest)
    usage = spelling if value is True else f"{spelling} {shlex.quote(str(value))}"
    print(f"Error: {spelling} takes no path; {' and '.join(ignored)} would be ignored.\n"
          f"Run it without one: reveal {usage}", file=sys.stderr)
    sys.exit(2)


def _flag_usage(dest: str, spelling: str) -> str:
    """The flag as it must be typed: with its metavar when it takes a value."""
    from ..parser import create_argument_parser
    for action in create_argument_parser('')._actions:
        if action.dest == dest and action.nargs != 0:
            return f"{spelling} {action.metavar or dest.upper()}"
    return spelling


def _handle_file_path(path: Path, element_from_path: Optional[str], args: 'Namespace') -> None:
    """Route a resolved file path — to ast query if convenience flags set, else normal handler."""
    if getattr(args, 'grep', None):
        if getattr(args, 'name', None):
            print(f"Note: --name '{args.name}' ignored when --grep is used (--grep searches all text, --name filters structural output)", file=sys.stderr)
        reject_unhonored_also_json(args, '--grep')
        handle_grep(to_posix(path), args.grep, args)
        return
    if getattr(args, 'name', None) or getattr(args, 'sort', None) or getattr(args, 'type', None):
        handle_uri(_build_ast_query_from_flags(path, args), args.element, args)
        return

    element = element_from_path or args.element
    if not element and getattr(args, 'section', None):
        if path.suffix.lower() in get_markdown_extensions():
            element = args.section
        else:
            print("❌ Error: --section only works with markdown files (.md, .markdown)", file=sys.stderr)
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print(f"  reveal {to_posix(path)}.md --section 'Heading Name'   # markdown section extraction", file=sys.stderr)
            print(f"  reveal {to_posix(path)} \"element_name\"                # for non-markdown, use element syntax", file=sys.stderr)
            print(file=sys.stderr)
            print("Learn more: reveal help://ux", file=sys.stderr)
            sys.exit(1)
    reject_unhonored_also_json(args, 'the file view')
    handle_file(str(path), element, args.meta, args.format, args)


def _run_check_with_ledger(args: 'Namespace') -> None:
    """``reveal PATH --check``: run check under the flag ledger, as ``reveal check PATH`` is.

    This route called run_check with no ledger, so a flag check never reads was dropped
    without a note: ``reveal f.py --outline --check`` printed exactly what ``--check``
    alone prints, and ``--help`` taught it as "Outline with quality checks" (BACK-1606).
    It takes the formats ``reveal check`` takes: ``--format typed`` printed text (BACK-1644).
    """
    from ...cli.commands.check import run_check
    from ..invocation import COMMANDS
    require_supported_format(args, COMMANDS['check'].formats, 'reveal --check')
    if ledger_of(args) is not None or not isinstance(args, Namespace):
        run_check(args)
        return
    ledger = FlagLedger(args, view='--check')
    args = ledger.track(args)
    mark(args, 'check')  # the flag that chose this route
    try:
        with ledger.dispatching(''):
            run_check(args)
        ledger.complete = True
    finally:
        if ledger.complete:
            ledger.report()


def handle_file_or_directory(path_str: str, args: 'Namespace') -> None:
    """Handle regular file or directory path.

    Args:
        path_str: Path string to file or directory
        args: Parsed arguments
    """
    if getattr(args, 'check', False):
        _run_check_with_ledger(args)
        return

    _guard_hotspots_flag(args, path_str)
    _guard_nginx_flags(args, path_str)
    _guard_ssl_flags(args)
    _guard_cpanel_flags(args)
    _guard_letsencrypt_flags(args)
    _guard_autossl_flags(args)
    _guard_related_flags(args, path_str)

    path, element_from_path = _parse_file_line_syntax(path_str)
    _validate_path_exists(path, path_str)

    if not path.is_dir() and not path.is_file():
        print(f"Error: {path_str} is neither file nor directory", file=sys.stderr)
        sys.exit(1)

    # BACK-1634: a flag the file or directory view never reads gets one note, as on the URI
    # form. The guards above run on the untracked args: they only reject a flag that belongs
    # to another route, and reading it there must not count as applying it.
    ledger = None
    if ledger_of(args) is None and isinstance(args, Namespace):
        ledger = FlagLedger(args, view='a directory listing' if path.is_dir() else 'the file view')
        args = ledger.track(args)
    try:
        with ledger.dispatching('') if ledger is not None else nullcontext():
            if path.is_dir():
                # The walk scope every entry point publishes (BACK-1581): --exclude plus
                # REVEAL_IGNORE, relative to this directory, as for a URI or a subcommand.
                from ...utils.exclusions import dispatch_scope, exclusion_scope
                with exclusion_scope(*dispatch_scope(str(path), peek(args, 'exclude'))):
                    _handle_directory_path(path, args)
            else:
                _handle_file_path(path, element_from_path, args)
        if ledger is not None:
            ledger.complete = True
    finally:
        if ledger is not None and ledger.complete:
            ledger.report()
