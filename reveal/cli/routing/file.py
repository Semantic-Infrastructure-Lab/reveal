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
from typing import Any, Callable, NoReturn, Optional

# Module-level imports so callers can mock reveal.cli.routing.file.handle_uri
# and reveal.cli.routing.file.handle_file in tests.
from .uri import handle_uri  # noqa: E402
from .declared import PathReadRefused, invalid_path_read, is_path_read, path_read_refusal  # noqa: E402
from .formats import (  # noqa: E402
    DEFAULT_OUTPUT_FORMATS, reject_unhonored_also_json, require_supported_format,
)
from ...file_handler import handle_file  # noqa: E402
from .grep import handle_grep, handle_grep_directory
from .ledger import FlagLedger, ledger_of, mark, peek  # noqa: E402
from ..defaults import _parser_defaults  # noqa: E402
from ..invocation import internal_request, typed_spelling  # noqa: E402
from ...utils.json_utils import json_answer  # noqa: E402
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


def _validate_path_exists(path: Path, path_str: str, element: Optional[str] = None, *, args=None) -> None:
    """Validate that path exists, providing helpful error messages. A missing path is refused as the path read's answer
    (``PathReadRefused``: this text, exit 2, its document in JSON; ``PathNotFoundError`` for the Python API)."""
    if not path.exists():
        from ...adapters.registry import list_supported_schemes
        if path_str in list_supported_schemes():
            target = shlex.quote(f'{path_str}://{element or "."}')
            _refuse(path_str, args, [f'Error: {path_str} is a URI noun: reveal {target}'], missing=True)
        cwd = os.getcwd()
        if ':' in path_str and re.search(r':\d+', path_str):
            base_path = path_str.rsplit(':', 1)[0]
            lines = [f"Error: {path_str} not found",
                     f"Hint: If extracting lines, use: reveal {base_path} :{path_str.rsplit(':', 1)[1]}"]
        else:
            abs_suggestion = os.path.join(cwd, path_str)
            lines = [f"Error: {path_str} not found", f"Hint: Running from {cwd}"]
            if abs_suggestion != path_str and os.path.exists(abs_suggestion):
                lines.append(f"      Try: reveal {abs_suggestion}")
        # D6: a missing path is an invalid resource (2), as in `reveal check` (BACK-2492).
        _refuse(path_str, args, lines, missing=True)


def _refuse(path_str: str, args, lines: list, *, exit_code: int = 2, missing: bool = False) -> NoReturn:
    """Refuse the path read with the site's own stderr *lines* and exit code (``declared.path_read_refusal``): the
    route answers it, emitted or handed to its answer consumer (BACK-2325). *missing*: the path does not exist, which
    the Python API raises as ``PathNotFoundError``."""
    from ...errors import PathNotFoundError
    text = '\n'.join(lines) + '\n'
    message = lines[0].removeprefix('Error: ')
    raise PathReadRefused(path_read_refusal(path_str, text, Namespace() if args is None else args, exit_code=exit_code,
                                            error=PathNotFoundError(message) if missing else None))


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
        from ...utils.results import ResultBuilder
        from ...reveal_types import CONTRACT_VERSION
        print(safe_json_dumps(json_answer(ResultBuilder.create(
            'directory_metadata', path, data=meta, source_type='directory',
            contract_version=CONTRACT_VERSION))))
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
        query_params.append(f"kind={args.type}")  # the canonical AST kind (BACK-2654: type is its legacy word)
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
    # A usage error (exit 2, D6) that names the command answering it (BACK-2621, B8).
    _refuse(path_str, args, [
        "❌ Error: --hotspots is not a path option: the hotspot ranking is the metrics noun's view", '',
        f"  reveal metrics {path_str} --view hotspots", f"  reveal 'metrics://{path_str}?view=hotspots'", '',
        "Learn more: reveal help://metrics"])


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
            # An invalid request, exit 2 (D6; it exited 1, BACK-2765).
            _refuse(path_str or getattr(args, 'path', None) or '', args, [
                f"❌ Error: {spec.flag} only works with {context}", '', "Examples:", spec.examples, '',
                f"Learn more: reveal help://{help_topic}"])


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
    _refuse(path_str, args, [
        f"❌ Error: {flag} only works with markdown files", '', "Examples:",
        "  reveal docs/ --related          # on a markdown directory",
        "  reveal doc.md --related         # on a .md file", '', "Learn more: reveal help://markdown"])


def _handle_directory_path(path: Path, args: 'Namespace', answer_consumer=None) -> None:
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
        handle_grep_directory(to_posix(path), args.grep, args, _parse_ext_arg(getattr(args, 'ext', None)),
                              answer_consumer=answer_consumer)
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
            with internal_request():
                handle_uri(_build_ast_query_from_flags(path, args), args.element, args, answer_consumer=answer_consumer)
            return
    elif getattr(args, 'name', None):
        with internal_request():
            handle_uri(_build_ast_query_from_flags(path, args), args.element, args, answer_consumer=answer_consumer)
        return
    require_supported_format(args, DEFAULT_OUTPUT_FORMATS, 'a directory listing')
    reject_unhonored_also_json(args, 'a directory listing')
    sort_by = getattr(args, 'sort', None)
    include_extensions = _parse_ext_arg(ext_from_args)
    output_format = getattr(args, 'format', 'text')
    listing = dict(respect_gitignore=args.respect_gitignore, exclude_patterns=args.exclude, sort_by=sort_by,
                   include_extensions=include_extensions, max_entries=args.max_entries)
    failures: list = []
    build: Callable[..., Any]
    if getattr(args, 'files', False):
        # --files defaults to newest-first; --asc flips it
        listing['sort_desc'] = not getattr(args, 'asc', False)
        build = show_file_list_json if output_format == 'json' else show_file_list
    else:
        listing.update(depth=args.depth if args.depth is not None else 3, fast=args.fast,
                       dir_limit=getattr(args, 'dir_limit', 0), sort_desc=getattr(args, 'desc', False),
                       failures=failures)
        build = show_directory_tree_json if output_format == 'json' else show_directory_tree
    _hand_off(_listing_answer(str(path), output_format, build, listing, failures), answer_consumer)


def _listing_answer(path: str, output_format: str, build, listing: dict, failures: list):
    """A directory listing (the tree, or ``--files``) as an Answer: its document in JSON, its text otherwise
    (BACK-2325: the Python API reads the document the CLI prints). *failures*: the files *build* could not read (the
    tree's line counts); a listing that lost one says so in itself and is incomplete, exit 3, as ``--grep`` on the same
    tree is (BACK-2520)."""
    from ...utils import safe_json_dumps
    from ...utils.results import AnalysisCompleteness, ExecutionFacts, execution_exit_code, note_incomplete
    from .uri import Answer
    built = build(path, **listing)
    # The text listing is its own walk and rendering, a string; an Answer's result is a dict (MCP reads its type).
    result = built if output_format == 'json' else {'text': built}
    facts = ExecutionFacts(AnalysisCompleteness.INCOMPLETE if failures else AnalysisCompleteness.COMPLETE)
    note_incomplete(result, facts)
    code = execution_exit_code(facts)

    def printer(_answer, **_options):
        print(safe_json_dumps(json_answer(result)) if output_format == 'json' else built)
        if code:
            sys.exit(code)
    document = (lambda: json_answer(result)) if output_format == 'json' else None
    return Answer(result, 'structure', printer, execution_facts=facts, document=document)


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

# Per-file views read only by the no-element structure view (display/formatting.py
# _build_analyzer_kwargs, display/structure.py) (dest -> spelling). Beside a NAMED element they
# are dropped with a ledger note ("--links has no effect on the file view", pinned by
# tests/test_multipath_section_back1728.py), so unlike ELEMENT_LESS_FLAGS they do not refuse an
# element; but when the "element" is an existing file it is a second path, and
# `reveal a.html b.html --metadata` looked for 'b.html' in a.html and never mentioned --metadata
# (BACK-1773). The parser's file-specific groups are checked against this table by
# tests/test_element_less_flags_back1773.py.
WHOLE_FILE_FLAGS = {
    'metadata': '--metadata', 'semantic': '--semantic', 'scripts': '--scripts', 'styles': '--styles',
    'links': '--links', 'link_type': '--link-type', 'broken_only': '--broken-only', 'domain': '--domain',
    'code': '--code', 'language': '--language', 'inline': '--inline', 'frontmatter': '--frontmatter',
    'related': '--related', 'related_all': '--related-all', 'related_flat': '--related-flat',
    'typed': '--typed', 'filter': '--filter',
    'server_name': '--server-name', 'log_path': '--log-path',
    'select': '--select', 'ignore': '--ignore', 'severity': '--severity', 'group': '--group',
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


# The ELEMENT_LESS_FLAGS that are early-exit modes dispatched before --stdin in main._SPECIAL_MODES:
# `--stdin` cannot reach them, so the pipe the other flags are pointed at is no answer for these
# (it scanned '.' for --decorator-stats and printed a usage line for the rest, BACK-1764).
STDIN_BLIND_FLAGS = frozenset({'explain_file', 'capabilities', 'show_ast', 'decorator_stats'})


def _given_flags(args: 'Namespace', table: dict) -> list:
    """The (dest, spelling) pairs of ``table`` the command line set: a value other than the parser's default, as the
    flag ledger reads it, so a switch typed off (``--group off``, default None) counts as given; the spelling is the
    one typed (``--no-group``)."""
    defaults = _parser_defaults()
    return [(dest, typed_spelling(dest, spelling)) for dest, spelling in table.items()
            if getattr(args, dest, None) not in (None, defaults.get(dest))]


def reject_ignored_element(args: 'Namespace') -> None:
    """Exit 2 when an element-less or element flag is given an element (a second path or ``file:N``).

    One disclosed refusal in place of a run that silently covers the first path only, or drops
    the flag's own element. URIs and ``@file`` lists read their second argument themselves and
    are left alone.
    """
    path_str = getattr(args, 'path', None)
    if not is_path_read(path_str):
        return
    declared = _given_flags(args, {**ELEMENT_LESS_FLAGS, **ELEMENT_FLAGS})
    whole_file = _given_flags(args, WHOLE_FILE_FLAGS)
    if not declared and not whole_file:
        return
    element = getattr(args, 'element', None) or _parse_file_line_syntax(path_str)[1]
    if not element:
        return
    if not declared and Path(element).exists():
        declared = whole_file  # the "element" is a second path; a named element only gets the ledger note
    if not declared:
        return
    dest, spelling = declared[0]
    if dest in ELEMENT_FLAGS:
        print(f"Error: {spelling} '{getattr(args, dest)}' and the element '{element}' both name what to "
              f"extract; one would be ignored.\nGive one of them: reveal reads one file and one element per call.",
              file=sys.stderr)
    elif dest in STDIN_BLIND_FLAGS:
        print(f"Error: {spelling} reads no element and covers one path per call; '{element}' would be ignored.\n"
              f"Run it once per path: for f in PATHS; do reveal {spelling} \"$f\"; done", file=sys.stderr)
    else:
        print(f"Error: {spelling} reads no element and covers one path per call; '{element}' would be ignored.\n"
              f"Run it once per path, or for several: ls PATHS | reveal --stdin {_flag_usage(dest, spelling)}",
              file=sys.stderr)
    sys.exit(2)


def reject_stdin_for_path_mode(args: 'Namespace', dest: str) -> None:
    """Exit 2 when ``--stdin`` is given beside a mode that reads one path (STDIN_BLIND_FLAGS).

    Those modes run before the stdin route, so the piped list was dropped: --decorator-stats
    scanned the current directory and exited 0.
    """
    if dest not in STDIN_BLIND_FLAGS or not getattr(args, 'stdin', False):
        return
    spelling = ELEMENT_LESS_FLAGS[dest]
    print(f"Error: {spelling} reads one path and cannot take --stdin; the piped list would be ignored.\n"
          f"Run it once per path: for f in PATHS; do reveal {spelling} \"$f\"; done", file=sys.stderr)
    sys.exit(2)


def reject_stdin_element_flag(args: 'Namespace') -> None:
    """Exit 2 when ``--stdin`` is given an ELEMENT_FLAGS flag such as ``--section``.

    The flag names one element of one file; the stdin route answers many paths and never applied
    it (`printf 'a.md\\n' | reveal --stdin --section X` printed the outline, BACK-1765).
    """
    for dest, spelling in ELEMENT_FLAGS.items():
        value = getattr(args, dest, None)
        if value:
            print(f"Error: {spelling} {shlex.quote(str(value))} names one element of one file; --stdin reads "
                  f"many paths, so it would be ignored.\nRun it once per path: "
                  f"for f in PATHS; do reveal \"$f\" {spelling} {shlex.quote(str(value))}; done", file=sys.stderr)
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
    """The flag as it must be typed: with its metavar when it takes a value (the action that spelling names)."""
    from ..parser import create_argument_parser
    parser = create_argument_parser('')
    named = parser._option_string_actions.get(spelling)
    for action in [named] if named is not None else parser._actions:
        if action.dest == dest and action.nargs != 0:
            return f"{spelling} {action.metavar or dest.upper()}"
    return spelling


def _handle_file_path(path: Path, element_from_path: Optional[str], args: 'Namespace', request=None,
                      answer_consumer=None) -> None:
    """Route a resolved file path — to ast query if convenience flags set, else normal handler. *request*: the bound
    element request (``_element_request``); binding refused a grep or query flag beside it (one answer per request)."""
    if getattr(args, 'grep', None):
        if getattr(args, 'name', None):
            print(f"Note: --name '{args.name}' ignored when --grep is used (--grep searches all text, --name filters structural output)", file=sys.stderr)
        reject_unhonored_also_json(args, '--grep')
        handle_grep(to_posix(path), args.grep, args, answer_consumer=answer_consumer)
        return
    if getattr(args, 'name', None) or getattr(args, 'sort', None) or getattr(args, 'type', None):
        with internal_request():
            handle_uri(_build_ast_query_from_flags(path, args), args.element, args, answer_consumer=answer_consumer)
        return

    element = element_from_path or args.element
    if not element and getattr(args, 'section', None):
        if path.suffix.lower() in get_markdown_extensions():
            element = args.section
        else:
            _refuse(args.path if is_path_read(getattr(args, 'path', None)) else to_posix(path), args, [
                "❌ Error: --section only works with markdown files (.md, .markdown)", '', "Examples:",
                f"  reveal {to_posix(path)}.md --section 'Heading Name'   # markdown section extraction",
                f"  reveal {to_posix(path)} \"element_name\"                # for non-markdown, use element syntax", '',
                "Learn more: reveal help://ux"])
    reject_unhonored_also_json(args, 'the file view')
    handle_file(str(path), element, args.meta, args.format, args, element_request=request,
                answer_consumer=answer_consumer)


def _run_check_with_ledger(args: 'Namespace') -> None:
    """``reveal PATH --check``: run check under the flag ledger, as ``reveal check PATH`` is.

    This route called run_check with no ledger, so a flag check never reads was dropped
    without a note: ``reveal f.py --outline --check`` printed exactly what ``--check``
    alone prints, and ``--help`` taught it as "Outline with quality checks" (BACK-1606).
    It takes the formats ``reveal check`` takes: ``--format typed`` printed text (BACK-1644).
    """
    from ...cli.commands.check import run_check
    from ..invocation import COMMANDS, retirement_note
    if not getattr(args, 'stdin', False):
        retirement_note('flag:--check')
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


# The main-parser inputs every element view reads beside the global options and the element declarations (the S3b-1
# measurement, BACK-2627 D3/U1): the fallback grammar switch, the walk policy the transitive views apply, and --stdin,
# whose batch routes each piped path here (an element view answers per line; BACK-2707 owns the batch).
_ELEMENT_READS = frozenset({'fallback', 'respect_gitignore', 'stdin'})


def _reject_unsupported_element_controls(args: 'Namespace') -> None:
    """D3/U1: an element request takes the global options, its own declarations and the measured reads; any other
    main-parser control it gives is an unsupported control (D18), exit 2, with the one shared message. The global
    ``--verbose`` is ``--detail full`` (rule 4), which element views do not declare: the shared ``verbose_binding``
    refuses it naming detail, as on a declared noun without detail."""
    from ...nav_params import ELEMENT_VIEW_SPECS
    from ...errors import NavRequestValidationError, RequestValidationError
    from ...utils.query_binding import legacy_flag_dests, unsupported_controls_message, verbose_binding
    from ..parser import _build_global_options_parser
    if getattr(args, 'verbose', False) is True:
        try:
            verbose_binding(ELEMENT_VIEW_SPECS)
        except RequestValidationError as exc:  # the nav owner's bounded origin: exit 2 on every transport
            raise NavRequestValidationError(str(exc)) from None
    accepted = {action.dest for action in _build_global_options_parser(main_modes=False)._actions} | _ELEMENT_READS
    accepted |= {'path', 'element', 'outline'} | {dest for spec in ELEMENT_VIEW_SPECS
                                                  for dest in ((spec.cli.dest if spec.cli else None) or spec.name,
                                                               *legacy_flag_dests(spec))}
    defaults = _parser_defaults()
    given = [typed_spelling(dest, '--' + dest.replace('_', '-')) for dest, value in vars(args).items()
             if dest in defaults and dest not in accepted and value not in (None, defaults[dest])]
    if given:
        raise NavRequestValidationError(unsupported_controls_message(ELEMENT_VIEW_SPECS, given))


def _note_element_retirements() -> None:
    """Each old element flag the request typed notes its RETIREMENTS row once, in the order typed; the set is the
    declarations' legacy flags (no hand list). The code-element ``--outline`` notes its target row once its element
    resolves (``file_handler._dispatch_nav``)."""
    from ...nav_params import ELEMENT_VIEW_SPECS
    from ..invocation import current_invocation, retired_flag_key, retirement_note
    legacy = {entry.flag for spec in ELEMENT_VIEW_SPECS for entry in spec.legacy if entry.flag}
    invocation = current_invocation()
    for token in invocation.argv if invocation is not None else ():
        if token == '--':
            break
        option = token.partition('=')[0]
        key = retired_flag_key(option) if option in legacy else None
        if key is not None:
            retirement_note(key)


def _element_request(path_str: str, args: 'Namespace'):
    """The bound element request of a path read (``nav_params.bind_element_request``), or None when the request gives no
    element control. Runs at the file route's entry, before the flag ledger and the directory branch: a directory
    refuses every element view, and every refusal is an invalid request (exit 2) naming what was given."""
    from ...file_handler import element_request_of
    path, element_from_path = _parse_file_line_syntax(path_str)
    element = element_from_path or getattr(args, 'element', None)
    request = element_request_of(str(path), element, args,
                                 before_binding=lambda: _reject_unsupported_element_controls(args))
    if request is not None:  # an invalid value refuses before the path is looked at, as argparse's types did
        _validate_path_exists(path, path_str, element, args=args)
        _note_element_retirements()
    return request


def _mark_element_controls(args: 'Namespace', request) -> None:
    """The element answer applies every control it bound: the ledger counts them read (the handlers read the request,
    not the namespace)."""
    from ...nav_params import ELEMENT_VIEW_SPECS
    from ...utils.query_binding import legacy_flag_dests
    if request is None:
        return
    dests = {dest for spec in ELEMENT_VIEW_SPECS
             for dest in ((spec.cli.dest if spec.cli else None) or spec.name, *legacy_flag_dests(spec))}
    mark(args, *(dest for dest in dests if peek(args, dest) is not None), *(('outline',) if peek(args, 'outline') else ()))


# The flags that turn the file view into a whole-file answer: an ast:// query or a text search.
_WHOLE_FILE_FLAGS = (('grep', '--grep'), ('name', '--name'), ('type', '--type'), ('sort', '--sort'))


def _reject_unread_element(path: Path, path_str: str, element: Optional[str], args: 'Namespace') -> None:
    """A positional element the chosen view never reads is an invalid request (D6 exit 2).

    ``reveal DIR NAME`` printed the tree and ``reveal FILE NAME --grep X`` (or ``--name``, ``--type``,
    ``--sort``) answered for the whole file, exit 0, without a word (BACK-2522). Runs on the untracked
    args, before the flag ledger: reading a flag here is not applying it."""
    if not element:
        return
    if path.is_dir():
        _refuse(path_str, args, [f"Error: {path_str} is a directory; it has no element '{element}'",
                                 f"Hint: name a file (reveal {path_str.rstrip('/')}/FILE {element}) or filter by name "
                                 f"(reveal {path_str} --name {element})"])
    flag = next((typed_spelling(dest, spelling) for dest, spelling in _WHOLE_FILE_FLAGS
                 if getattr(args, dest, None)), None)
    if flag:
        _refuse(path_str, args, [f"Error: {flag} answers for the whole of {path_str}; it does not select '{element}'",
                                 f"Hint: drop '{element}' to search or query the file, or drop {flag} to show '{element}'"])


def handle_file_or_directory(path_str: str, args: 'Namespace', *, answer_consumer=None) -> None:
    """Handle regular file or directory path. A refusal of the request (``RequestValidationError``: the binder, the
    element request's own checks, the configuration it reads) in a JSON request answers with the path read's
    invalid-request document, exit 2, as a declared noun's does (BACK-2756 cell 21j), and a configuration that could
    not be loaded with the failed answer, exit 3; in text mode each goes on to the process's ``error:`` line unchanged.
    A refusal at one of the route's own sites (``PathReadRefused``) prints its text, and its document in JSON. A
    spelling at the error stage (``RetiredSpellingError``) answers in JSON with the same document saying its row's text
    (``answer_retired_spelling``, BACK-2627), and in text mode, as for the API, goes on unchanged.

    Args:
        path_str: Path string to file or directory
        args: Parsed arguments
        answer_consumer: Receives each Answer the path read gives (the file structure, the tree, a refusal) instead
            of its being emitted, as ``handle_uri`` hands its answers (the Python API, BACK-2325)
    """
    from ...errors import ConfigLoadError, RequestValidationError
    from ..invocation import RetiredSpellingError
    from .declared import answer_retired_spelling
    try:
        _handle_file_or_directory(path_str, args, answer_consumer)
    except PathReadRefused as refused:
        _hand_off(refused.answer, answer_consumer)
    except RetiredSpellingError as exc:
        answer_retired_spelling(exc, args, lambda text: invalid_path_read(path_str, text, args), answer_consumer)
    except (RequestValidationError, ConfigLoadError) as exc:
        if answer_consumer is None and getattr(args, 'format', None) != 'json':
            raise
        answer = invalid_path_read(path_str, str(exc), args, error=exc)
        if answer is None:
            raise
        _hand_off(answer, answer_consumer)
        if answer_consumer is None:
            sys.exit(2)  # emit exits with the answer's outcome; this is the usage exit if it did not


def _hand_off(answer, answer_consumer) -> None:
    """The path read's answer to its consumer, or emitted (printed, then the exit its outcome says)."""
    if answer_consumer is None:
        answer.emit()
    else:
        answer_consumer(answer)


def _handle_file_or_directory(path_str: str, args: 'Namespace', answer_consumer=None) -> None:
    from ...config import require_selected_config
    require_selected_config()  # on every path read, read or not, as on every noun (BACK-2677, BACK-2756 cell 22)
    request = _element_request(path_str, args)

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
    _validate_path_exists(path, path_str, getattr(args, 'element', None), args=args)

    if not path.is_dir() and not path.is_file():
        # D6: a path that is neither (a named pipe, a socket) is an invalid resource, 2, not the findings code 1.
        _refuse(path_str, args, [f"Error: {path_str} is neither file nor directory"])
    _reject_unread_element(path, path_str, element_from_path or getattr(args, 'element', None), args)

    # BACK-1634: a flag the file or directory view never reads gets one note, as on the URI
    # form. The guards above run on the untracked args: they only reject a flag that belongs
    # to another route, and reading it there must not count as applying it.
    ledger = None
    if ledger_of(args) is None and isinstance(args, Namespace):
        ledger = FlagLedger(args, view='a directory listing' if path.is_dir() else 'the file view')
        args = ledger.track(args)
        _mark_element_controls(args, request)
    try:
        with ledger.dispatching('') if ledger is not None else nullcontext():
            if path.is_dir():
                # The walk scope every entry point publishes (BACK-1581): --exclude plus
                # REVEAL_IGNORE, relative to this directory, as for a URI or a subcommand.
                from ...utils.exclusions import dispatch_scope, exclusion_scope
                with exclusion_scope(*dispatch_scope(str(path), peek(args, 'exclude'))):
                    _handle_directory_path(path, args, answer_consumer)
            else:
                _handle_file_path(path, element_from_path, args, request, answer_consumer)
        if ledger is not None:
            ledger.complete = True
    finally:
        if ledger is not None and ledger.complete:
            ledger.report()
