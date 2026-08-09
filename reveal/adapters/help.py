"""Help adapter (help://) - Meta-adapter for exploring reveal's capabilities."""

import re
import sys
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Dict, List, Any, Optional
from .base import ResourceAdapter, Stability, register_adapter, register_renderer, _ADAPTER_REGISTRY
from ..rendering import render_help
from ..utils.results import ResultBuilder
from reveal.reveal_types import CONTRACT_VERSION

# Valid help_category values for the help:// index listing.
# Guides without help_category (or with an unknown value) are accessible by
# topic name but don't appear in the index — same as today's uncategorized
# behavior, but now explicit rather than accidental.
VALID_HELP_CATEGORIES = {
    'getting_started',
    'ai_guides',
    'feature_guides',
    'best_practices',
    'dev_guides',
}


def _read_help_frontmatter(path: Path) -> Dict[str, str]:
    """Extract help_* fields from a markdown file's YAML frontmatter.

    Returns an empty dict if the file has no frontmatter or yaml parsing fails.
    Only the four help_* fields are read; other frontmatter is ignored.

    Fields:
        help_topic        Canonical topic for index display (optional). If set,
                          only this topic gets help_category — other aliases of
                          the same file remain reachable but stay out of the index.
        help_description  One-line description shown in the help index.
        help_category     One of VALID_HELP_CATEGORIES; absent or empty hides
                          the topic from the index but keeps direct access.
        help_token_estimate  Rough token cost of the full guide, e.g. "~3,000".
    """
    # Lazy import — yaml isn't needed unless the help adapter is instantiated,
    # and we want to keep this helper testable in isolation from the markdown
    # adapter's frontmatter machinery.
    from .markdown.files import extract_frontmatter
    fm = extract_frontmatter(path) or {}
    return {
        k: str(fm[k])
        for k in ('help_topic', 'help_description', 'help_category', 'help_token_estimate')
        if k in fm and fm[k] is not None
    }


def _strip_frontmatter(content: str) -> str:
    """Remove a leading YAML front-matter block (``---`` … ``---``) from text.

    Guides start with front matter consumed by the topic registry; it must not
    appear in rendered help. Returns *content* unchanged if it does not open
    with a front-matter fence.
    """
    if not content.startswith('---'):
        return content
    lines = content.splitlines()
    # First line is the opening fence; find the closing fence.
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            # Drop fences + body, plus a single trailing blank line if present.
            rest = lines[i + 1:]
            if rest and rest[0].strip() == '':
                rest = rest[1:]
            return '\n'.join(rest)
    return content  # No closing fence — leave content untouched.


@dataclass(frozen=True)
class GuideEntry:
    """Registered help topic with metadata sourced from guide frontmatter.

    A single guide file can be reached via multiple topics (aliases). All
    topics for the same file share the same description/category/token_estimate
    pulled from that file's frontmatter — the renderer dedupes by file path
    when building the index.
    """
    topic: str
    file: str               # relative path under reveal/docs/
    description: str = ""
    category: str = ""      # one of VALID_HELP_CATEGORIES, or "" to hide from index
    token_estimate: str = ""
    # BACK-931: True when another topic is this file's canonical name. Computed
    # in _discover_and_merge_guides, not here — a single entry can't know about
    # its siblings at construction time. Lets audits (e.g. topic-reachability
    # completeness checks) filter the ~40 alias topics (ast-adapter, mcp-setup,
    # ...) out of _list_topics() without changing what _list_topics() itself
    # returns (aliases must stay resolvable for typo-suggestion matching).
    is_alias: bool = False

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

_EXAMPLE_RECIPES: Dict[str, Dict[str, Any]] = {
    'security': {
        'type': 'query_recipes',
        'task': 'security',
        'description': 'Security analysis and vulnerability detection',
        'recipes': [
            {'goal': 'Find authentication functions', 'query': 'ast://src?name~=auth&type=function', 'description': 'Locate authentication-related code', 'output_type': 'ast_query'},
            {'goal': 'Check SSL certificate expiry', 'query': 'ssl://example.com --expiring-within=30', 'description': 'Find certificates expiring soon', 'output_type': 'ssl_certificate'},
            {'goal': 'Find SQL query construction', 'query': 'ast://src?name~=query&complexity>5', 'description': 'Locate complex database queries (SQL injection risk)', 'output_type': 'ast_query'},
            {'goal': 'Map the external attack surface', 'query': 'surface://src', 'description': 'Every CLI, HTTP route, env var, network call, and filesystem write the system touches — taxonomy-based, project-specific clients outside known libraries not detected', 'output_type': 'surface_scan'},
        ]
    },
    'codebase': {
        'type': 'query_recipes',
        'task': 'codebase',
        'description': 'Codebase exploration and understanding',
        'recipes': [
            {'goal': 'Get project overview', 'query': 'reveal src/', 'description': 'Progressive disclosure: structure first', 'output_type': 'reveal_structure'},
            {'goal': 'Find entry points', 'query': 'ast://src?name=main*&type=function', 'description': 'Locate main() and main_* entry point functions', 'output_type': 'ast_query'},
            {'goal': 'List all classes', 'query': 'ast://src?type=class&sort=name', 'description': 'Enumerate class hierarchy for structural overview', 'output_type': 'ast_query'},
            {'goal': 'Find complex code', 'query': 'ast://src?complexity>15', 'description': 'Locate high-complexity functions', 'output_type': 'ast_query'},
            {'goal': 'Find architectural seams', 'query': 'contracts://src', 'description': 'ABCs, Protocols, TypedDicts, dataclasses, BaseModels — where the interface boundaries are', 'output_type': 'contracts'},
        ]
    },
    'due-diligence': {
        'type': 'query_recipes',
        'task': 'due-diligence',
        'description': 'Technical due-diligence workflow — orient, find risk, quantify coupling, blast-radius, dead code, test honesty (run in order)',
        'recipes': [
            {'goal': '1. Orient in 60 seconds', 'query': 'reveal overview <repo>', 'description': 'Counts, language mix, quality, top hotspots, architecture summary in one command. On multi-million-line repos this can take minutes — skip to the targeted steps below', 'output_type': 'overview'},
            {'goal': '2. Where is the risk concentrated', 'query': "reveal 'ast://<repo>?complexity>25&sort=-complexity'", 'description': 'The files/functions carrying disproportionate complexity — where future incidents will trace back to (also: reveal hotspots <repo>)', 'output_type': 'ast_query'},
            {'goal': '3. How coupled is it', 'query': "reveal 'imports://<repo>?circular=true'", 'description': 'Circular-dependency groups — a concrete, checkable architectural-debt number for a DD memo', 'output_type': 'circular_dependencies'},
            {'goal': '4. What is everything built on', 'query': 'reveal architecture <repo>', 'description': 'Entry points, core abstractions (by fan-in), risks, and suggested next commands in one brief — changing a core abstraction\'s contract is the highest-blast-radius work. For a token-budgeted LLM context snapshot boosted the same way, use reveal pack <repo> --architecture instead', 'output_type': 'architecture'},
            {'goal': '5. If I touch this, what breaks', 'query': "reveal 'depends://<repo>/<module>'", 'description': 'Who imports this module (blast radius). For a function: reveal <repo>/<file> <fn> --sideeffects (note: intra-procedural only — "none" means none in this body, not safe to change)', 'output_type': 'module_dependents'},
            {'goal': "6. What's dead or duplicated", 'query': "reveal 'calls://<repo>?uncalled=true&type=function'", 'description': 'Statically-uncalled functions (test-runner entry points excluded by default; add &test-framework=true to include). Also: reveal check <repo> --select B,C,D,I,U for duplicates', 'output_type': 'calls_uncalled'},
            {'goal': '7. Is the test suite honest', 'query': "reveal 'patches://<repo>/tests?group=target&limit=15'", 'description': 'Mock/patch-pressure grouped by target (Python/TS-JS) — which boundaries are over-mocked, a test-trust smell', 'output_type': 'patches_scan'},
            {'goal': '8. Did recent changes hold up', 'query': 'reveal review <old-tag>..<new-tag>', 'description': 'Quality + structural assessment over a git range (or main..feature for an open PR) — CLI subcommand, no URI adapter form'},
            {'goal': '9. Diff structure across two revisions', 'query': "reveal 'diff://<repo>/<file>@<refA>::<repo>/<file>@<refB>'", 'description': 'Structural diff between two revisions of a file. For a whole-repo architecture delta, use reveal architecture <repo> --against <ref> instead', 'output_type': 'diff_comparison'},
            {'goal': 'Bonus: curate an LLM-ready context snapshot', 'query': 'reveal pack <repo> --architecture', 'description': 'Token-budgeted export of the whole tree, boosted toward the same core abstractions step 4 identifies — for handing the codebase to another agent, not for the DD memo itself', 'output_type': 'pack'},
        ]
    },
    'debugging': {
        'type': 'query_recipes',
        'task': 'debugging',
        'description': 'Debugging and error investigation',
        'recipes': [
            {'goal': 'Find error handlers', 'query': 'ast://src?name~=error&type=function', 'description': 'Locate error handling code', 'output_type': 'ast_query'},
            {'goal': 'Check recent changes', 'query': 'git://.?type=history', 'description': 'Review recent commit history', 'output_type': 'git_ref'},
            {'goal': 'Find large functions', 'query': 'ast://src?lines>100&type=function', 'description': 'Locate potentially problematic large functions', 'output_type': 'ast_query'},
            {'goal': 'Walk the call chain from an entry point', 'query': 'trace://src?from=main', 'description': 'Depth-indented execution narrative built on calls:// BFS — see the actual path a bug report walks', 'output_type': 'trace'},
        ]
    },
    'quality': {
        'type': 'query_recipes',
        'task': 'quality',
        'description': 'Code quality and hotspot analysis',
        'recipes': [
            {'goal': 'Find quality hotspots', 'query': 'hotspots://src', 'description': 'File- and function-level hotspots in one ranked list — composes stats:// (file quality) and ast:// (function complexity) so you don\'t have to run both yourself', 'output_type': 'hotspots_scan'},
            {'goal': 'Get an overall quality score', 'query': 'stats://src', 'description': 'Codebase-wide metrics — lines, functions, quality score — the raw numbers hotspots:// ranks against', 'output_type': 'stats_summary'},
            {'goal': 'Check code complexity', 'query': 'ast://src?complexity>10', 'description': 'High complexity functions', 'output_type': 'ast_query'},
            {'goal': 'Find long functions lacking simplicity', 'query': 'ast://src?type=function&lines>50&sort=-lines', 'description': 'Large functions sorted by size — prime documentation/refactor targets', 'output_type': 'ast_query'},
            {'goal': 'Dependency health at a glance', 'query': 'deps://src', 'description': 'External packages, circular deps, unused imports — a dashboard composed from three imports:// queries, for when you want the summary not the raw graph', 'output_type': 'deps_scan'},
            {'goal': 'Where test mocking hides real coupling', 'query': 'testability://src', 'description': 'Joins test patch/mock pressure with production boundary fan-out — over-mocked boundaries are untested boundaries', 'output_type': 'testability_report'},
        ]
    },
    'infrastructure': {
        'type': 'query_recipes',
        'task': 'infrastructure',
        'description': 'Server infrastructure inspection — nginx, SSL, domains',
        'recipes': [
            {'goal': 'Inspect nginx vhost', 'query': 'nginx://example.com', 'description': 'Ports, upstreams, auth, locations for a domain', 'output_type': 'nginx_vhost_summary'},
            {'goal': 'List all nginx vhosts', 'query': 'nginx://', 'description': 'Overview of all enabled nginx sites', 'output_type': 'nginx_sites_overview'},
            {'goal': 'Check nginx upstream health', 'query': 'nginx://example.com/upstream', 'description': 'TCP reachability of proxy_pass backends', 'output_type': 'nginx_vhost_upstream'},
            {'goal': 'Check SSL certificate', 'query': 'ssl://example.com --check', 'description': 'Certificate health, expiry, chain validity', 'output_type': 'ssl_certificate'},
            {'goal': 'Validate nginx SSL certs from config', 'query': 'ssl://nginx:///etc/nginx/conf.d/*.conf --check --local-certs', 'description': 'Check cert files referenced by nginx (no network)', 'output_type': 'ssl_certificate'},
            {'goal': 'Domain health check', 'query': 'domain://example.com --check', 'description': 'DNS propagation, SSL status, registration info', 'output_type': 'domain_health'},
            {'goal': 'Check cPanel AutoSSL run outcomes', 'query': 'autossl://latest?only-failures', 'description': 'Most recent AutoSSL run, failures only — per-domain DCV/TLS outcomes without wading through the passing domains', 'output_type': 'autossl_run'},
            {'goal': 'Full cPanel user audit', 'query': 'cpanel://johndoe/full-audit', 'description': 'One-shot composite: SSL + ACL + nginx ACME readiness; exits 2 on any failure (add --format=json for scripting)', 'output_type': 'cpanel_full_audit'},
            {'goal': "Find Let's Encrypt cert issues", 'query': 'letsencrypt:// --check-orphans', 'description': 'Certs not referenced by any nginx ssl_certificate directive — renewal candidates nobody is using (also: --check-duplicates for identical-SAN certs)', 'output_type': 'letsencrypt_inventory'},
        ]
    },
    'documentation': {
        'type': 'query_recipes',
        'task': 'documentation',
        'description': 'Documentation search and analysis — markdown, front matter',
        'recipes': [
            {'goal': 'Find docs by topic in body', 'query': "reveal 'markdown://docs/?body-contains=nginx'", 'description': 'Search doc body text (after frontmatter)', 'output_type': 'markdown_query'},
            {'goal': 'Find all guides', 'query': "reveal 'markdown://docs/?type=guide'", 'description': 'Filter by frontmatter field value', 'output_type': 'markdown_query'},
            {'goal': 'Find recent docs about deployment', 'query': "reveal 'markdown://docs/?body-contains=deploy&sort=-modified&limit=10'", 'description': 'Body search with recency sort', 'output_type': 'markdown_query'},
            {'goal': 'Rank multi-word body search, best match first', 'query': "reveal 'markdown://docs/?body-contains=auth&body-contains=token&explain'", 'description': 'Results sort by relevance_score (term frequency + heading proximity); the explain param adds a per-term score breakdown', 'output_type': 'markdown_query'},
            {'goal': 'Validate internal links', 'query': 'reveal docs/README.md --links --link-type internal', 'description': 'Find broken internal links in a doc', 'output_type': 'markdown_query'},
            {'goal': 'Get document outline', 'query': 'reveal docs/README.md --outline', 'description': 'Hierarchical heading tree', 'output_type': 'markdown_query'},
            {'goal': 'Who links to this doc before I rename/move it', 'query': "reveal 'markdown://docs/?backlinks=auth.md'", 'description': 'Cheap single-doc pre-edit staleness check', 'output_type': 'markdown_backlinks'},
            {'goal': 'Whole-tree link graph (forward + backlinks + orphans)', 'query': "reveal 'markdown://docs/?link-graph'", 'description': 'Every doc\'s inbound/outbound edges in one call', 'output_type': 'markdown_link_graph'},
            {'goal': 'Frontmatter maintenance queue', 'query': "reveal 'markdown://docs/?lint'", 'description': 'Malformed YAML and no-frontmatter files, one list not one-file-at-a-time', 'output_type': 'markdown_frontmatter_lint'},
            {'goal': 'Frontmatter queue including missing required fields', 'query': "reveal 'markdown://docs/?lint&lint-fields=title,type'", 'description': 'Same queue, also flags files missing title/type', 'output_type': 'markdown_frontmatter_lint'},
        ]
    },
    'sessions': {
        'type': 'query_recipes',
        'task': 'sessions',
        'description': 'Claude Code session analysis — tool usage, files, errors, workflows',
        'recipes': [
            {'goal': 'Session overview', 'query': 'reveal claude://session/my-session', 'description': 'Message count, tool calls, duration, tool summary', 'output_type': 'claude_overview'},
            {'goal': 'Search across all sessions', 'query': "reveal 'claude://sessions/?search=validate_token'", 'description': 'Cross-session content search', 'output_type': 'claude_cross_session_search'},
            {'goal': 'Session tool usage', 'query': 'reveal claude://session/my-session/tools', 'description': 'Tool call counts and success rates', 'output_type': 'claude_tools'},
            {'goal': 'Files touched in a session', 'query': 'reveal claude://session/my-session/files', 'description': 'All Read/Write/Edit operations', 'output_type': 'claude_files'},
            {'goal': 'Session errors', 'query': 'reveal claude://session/my-session?errors', 'description': 'All errors with context', 'output_type': 'claude_errors'},
            {'goal': 'Prompt/answer pairs for a session', 'query': 'reveal claude://session/my-session/exchanges', 'description': 'Each human prompt paired with the assistant\'s final answer, skipping thinking-only and tool-only turns in between', 'output_type': 'claude_exchanges'},
            {'goal': 'Codex session overview', 'query': 'reveal codex://SESSION-ID', 'description': 'Turns, tools, tokens, duration for a Codex CLI session', 'output_type': 'codex_session_overview'},
            {'goal': 'Filter Codex sessions by title', 'query': "reveal 'codex://sessions/?filter=validate_token'", 'description': 'Metadata filter by title or first message (SQLite index, no JSONL scan)', 'output_type': 'codex_session_list'},
            {'goal': 'Full-text search across Codex content', 'query': "reveal 'codex://sessions/?search=authentication'", 'description': 'Scan JSONL event files for a term', 'output_type': 'codex_content_search'},
        ]
    },
    'history': {
        'type': 'query_recipes',
        'task': 'history',
        'description': 'Prompt history and session discovery across all projects',
        'recipes': [
            {'goal': 'Recent prompts', 'query': 'reveal claude://history', 'description': 'Last 50 prompts across all projects', 'output_type': 'claude_history'},
            {'goal': 'Search prompt history', 'query': "reveal 'claude://history?search=deploy&since=2026-03-01'", 'description': 'Filter prompts by keyword and date', 'output_type': 'claude_history'},
            {'goal': 'Prompts for a specific project', 'query': "reveal 'claude://history?project=my-project'", 'description': 'Scope history to one project', 'output_type': 'claude_history'},
            {'goal': 'List all sessions', 'query': 'reveal claude://sessions/', 'description': 'All sessions with metadata', 'output_type': 'claude_session_list'},
        ]
    },
    'data': {
        'type': 'query_recipes',
        'task': 'data',
        'description': 'Database and structured data inspection — SQLite, MySQL, Excel',
        'recipes': [
            {'goal': 'List database tables', 'query': 'reveal sqlite:///path/to/app.db', 'description': 'Schema overview with row counts', 'output_type': 'sqlite_database'},
            {'goal': 'Inspect a table', 'query': 'reveal sqlite:///path/to/app.db/users', 'description': 'Column types, constraints, sample rows', 'output_type': 'sqlite_table'},
            {'goal': 'MySQL database overview', 'query': 'reveal mysql://user:pass@host/dbname', 'description': 'Tables, row counts, schema summary', 'output_type': 'mysql_health'},
            {'goal': 'Inspect an Excel workbook', 'query': 'reveal xlsx:///path/to/data.xlsx', 'description': 'Sheet names, dimensions, header rows (the .xlsx extension auto-routes here too — reveal data.xlsx works the same)', 'output_type': 'xlsx_workbook'},
            {'goal': 'Query a JSON file by path', 'query': 'json://config.json?flatten', 'description': 'Flatten to grep-able dotted-path format (also: ?schema for type structure, ?gron as an alias for ?flatten)', 'output_type': 'json_flatten'},
        ]
    },
    'runtime': {
        'type': 'query_recipes',
        'task': 'runtime',
        'description': 'Runtime environment — env vars, Python packages, reveal install state',
        'recipes': [
            {'goal': 'All environment variables', 'query': 'reveal env://', 'description': 'Full env dump grouped by prefix', 'output_type': 'environment'},
            {'goal': 'Filter env by prefix', 'query': "reveal 'env://?prefix=DB'", 'description': 'Show only DB_* variables', 'output_type': 'environment'},
            {'goal': 'Python package versions', 'query': 'reveal python://', 'description': 'Installed packages with versions', 'output_type': 'python_runtime'},
            {'goal': 'Reveal install info', 'query': 'reveal reveal://', 'description': 'Registered analyzers, adapters, rules', 'output_type': 'reveal_structure'},
        ]
    },
}


class HelpRenderer:
    """Renderer for help system results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render help topic list.

        Args:
            result: Structure dict from HelpAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        render_help(result, format, list_mode=True)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific help topic.

        Args:
            result: Element dict from HelpAdapter.get_element()
            format: Output format ('text', 'json', 'grep')
        """
        render_help(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error accessing help: {error}", file=sys.stderr)


@register_adapter('help')
@register_renderer(HelpRenderer)
class HelpAdapter(ResourceAdapter):
    """Adapter for exploring reveal's help system via help:// URIs.

    Examples:
        help://                    # List all help topics
        help://ast                 # Get ast:// adapter help
        help://ast/workflows       # Just the workflows section
        help://ast/try-now         # Just the try-now examples

        help://ast/anti-patterns   # Just the anti-patterns
        help://env                 # Get env:// adapter help
        help://python-guide        # Python adapter comprehensive guide
        help://markdown            # Markdown features guide
        help://tricks              # Cool tricks and hidden features
        help://adapters            # List all adapters with help
        help://quick               # Quick-reference cheat sheet (top 10 commands)
        help://agent               # Agent usage guide (AGENT_HELP.md)

    Agent Introspection (v0.46.0+):
        help://schemas/ssl         # Machine-readable schema for ssl:// adapter
        help://schemas/ast         # Machine-readable schema for ast:// adapter
        help://examples/security   # Query recipes for security analysis
        help://examples/codebase   # Query recipes for codebase exploration
    """

    STABILITY = Stability.STABLE
    ELEMENT_NAMESPACE_ADAPTER = True
    LEGACY_INIT = False
    CANONICAL_EMPTY_RESOURCE = ''

    # Valid section names for help://adapter/section queries
    VALID_SECTIONS = {'workflows', 'try-now', 'anti-patterns'}

    # Static help files (markdown documentation in reveal/docs/)
    STATIC_HELP = {
        # Top-level docs (reveal/docs/)
        'intro': 'QUICK_START.md',
        'quick-start': 'QUICK_START.md',  # legacy alias for 'intro' — kept resolvable, not shown in index
        'agent': 'AGENT_HELP.md',
        'anti-patterns': 'AGENT_HELP.md',  # Merged into AGENT_HELP.md
        'benchmarks': 'BENCHMARKS.md',
        'output-diagnostics': 'OUTPUT_DIAGNOSTICS_GUIDE.md',
        # Adapter guides (reveal/docs/adapters/)
        'architecture': 'adapters/ARCHITECTURE_ADAPTER_GUIDE.md',
        'ast': 'adapters/AST_ADAPTER_GUIDE.md',
        'autossl': 'adapters/AUTOSSL_ADAPTER_GUIDE.md',
        'calls': 'adapters/CALLS_ADAPTER_GUIDE.md',
        'claude': 'adapters/CLAUDE_ADAPTER_GUIDE.md',
            'codex': 'adapters/CODEX_ADAPTER_GUIDE.md',
        'contracts': 'adapters/CONTRACTS_ADAPTER_GUIDE.md',
        'cpanel': 'adapters/CPANEL_ADAPTER_GUIDE.md',
        'deps': 'adapters/DEPS_ADAPTER_GUIDE.md',
        'depends': 'adapters/DEPENDS_ADAPTER_GUIDE.md',
        'diff': 'adapters/DIFF_ADAPTER_GUIDE.md',
        'domain': 'adapters/DOMAIN_ADAPTER_GUIDE.md',
        'env': 'adapters/ENV_ADAPTER_GUIDE.md',
        'git': 'adapters/GIT_ADAPTER_GUIDE.md',
        'hotspots': 'adapters/HOTSPOTS_ADAPTER_GUIDE.md',
        'html': 'adapters/HTML_GUIDE.md',
        'imports': 'adapters/IMPORTS_ADAPTER_GUIDE.md',
        'json': 'adapters/JSON_ADAPTER_GUIDE.md',
        'letsencrypt': 'adapters/LETSENCRYPT_ADAPTER_GUIDE.md',
        'markdown': 'adapters/MARKDOWN_GUIDE.md',
        'mysql': 'adapters/MYSQL_ADAPTER_GUIDE.md',
        'nginx': 'adapters/NGINX_GUIDE.md',
        'overview': 'adapters/OVERVIEW_ADAPTER_GUIDE.md',
        'patches': 'adapters/PATCHES_ADAPTER_GUIDE.md',
        'python': 'adapters/PYTHON_ADAPTER_GUIDE.md',
        # 'python-guide' (not 'python') is the canonical topic below — pre-dates
        # the bare 'python' alias (added v0.18.0), deeply referenced as *the*
        # documented example of the feature_guides convention (AGENT_HELP.md,
        # HELP_SYSTEM_GUIDE.md, test_rendering_help.py) — kept as-is. No other
        # adapter guide has a bare+'-guide' duplicate pair except 'reveal-guide'
        # (which has no bare form to collide with). Removed 'patches-guide'
        # (BACK-479): added in v0.94.0 by copying this naming pattern, but never
        # referenced anywhere outside this dict — pure dead duplicate of 'patches'.
        'python-guide': 'adapters/PYTHON_ADAPTER_GUIDE.md',
        'reveal-guide': 'adapters/REVEAL_ADAPTER_GUIDE.md',
        'sqlite': 'adapters/SQLITE_ADAPTER_GUIDE.md',
        'ssl': 'adapters/SSL_ADAPTER_GUIDE.md',
        'stats': 'adapters/STATS_ADAPTER_GUIDE.md',
        'surface': 'adapters/SURFACE_ADAPTER_GUIDE.md',
        'trace': 'adapters/TRACE_ADAPTER_GUIDE.md',
        'xlsx': 'adapters/XLSX_ADAPTER_GUIDE.md',
        # User guides (reveal/docs/guides/)
        'ci': 'guides/CI_RECIPES.md',
        'codebase-review': 'guides/RECIPES.md',  # CODEBASE_REVIEW.md archived; content merged into RECIPES.md
        'config': 'guides/CONFIGURATION_GUIDE.md',
        'configuration': 'guides/CONFIGURATION_GUIDE.md',
        'dev': 'guides/SUBCOMMANDS_GUIDE.md',
        'duplicate-detection': 'guides/DUPLICATE_DETECTION_GUIDE.md',
        'duplicates': 'guides/DUPLICATE_DETECTION_GUIDE.md',
        'elements': 'guides/ELEMENT_DISCOVERY_GUIDE.md',
        'fields': 'guides/FIELD_SELECTION_GUIDE.md',
        'health': 'guides/SUBCOMMANDS_GUIDE.md',
        'mcp': 'guides/MCP_SETUP.md',
        'mcp-setup': 'guides/MCP_SETUP.md',
        'nav': 'guides/NAV_GUIDE.md',
        'navigation': 'guides/NAV_GUIDE.md',
        'pack': 'guides/SUBCOMMANDS_GUIDE.md',
        'query': 'guides/QUERY_SYNTAX_GUIDE.md',
        'query-params': 'guides/QUERY_PARAMETER_REFERENCE.md',
        'recipes': 'guides/RECIPES.md',  # alias only — see 'tricks' below for canonical
        'review': 'guides/SUBCOMMANDS_GUIDE.md',
        'schema': 'guides/SCHEMA_VALIDATION_HELP.md',
        'subcommands': 'guides/SUBCOMMANDS_GUIDE.md',  # canonical; dev/health/pack/review are aliases
        # Note: 'schemas' is intentionally NOT in STATIC_HELP — the dynamic handler
        # at render_element intercepts help://schemas to list adapter schemas (machine-readable).
        # Use help://schema (singular) to reach SCHEMA_VALIDATION_HELP.md.
        'testability': 'guides/TESTABILITY_GUIDE.md',
        # 'tricks' (not 'recipes', despite the file being titled/named "Reveal
        # Recipes") is the canonical topic — kept deliberately per
        # BACK-479 review: 'tricks' is the established public name, referenced
        # 20+ times across docs/adapter examples/tests (including exact-string
        # test assertions in test_rendering_help.py, test_adapter_integration.py);
        # 'recipes' appears almost nowhere. Flipping would touch ~20 files for
        # no discoverability gain. See RECIPES.md's own help_topic: tricks.
        'tricks': 'guides/RECIPES.md',   # Merged into RECIPES.md (task-based workflows)
        'ux': 'guides/UX_GUIDE.md',
        'what-is': 'guides/WHAT_IS_REVEAL_GOOD_FOR.md',
        'why': 'WHY_REVEAL.md',
        # Development docs (reveal/docs/development/)
        'adapter-authoring': 'development/ADAPTER_AUTHORING_GUIDE.md',
        'adapter-consistency': 'development/ADAPTER_CONSISTENCY.md',
        'analyzer-patterns': 'development/ANALYZER_PATTERNS.md',
        'cli-integration': 'development/CLI_INTEGRATION_GUIDE.md',
        'contract-versions': 'development/CONTRACT_VERSIONS.md',
        'elixir': 'development/ELIXIR_ANALYZER_GUIDE.md',
        'help': 'development/HELP_SYSTEM_GUIDE.md',
        'output': 'development/OUTPUT_CONTRACT.md',
        'rule-authoring': 'development/RULE_AUTHORING_GUIDE.md',
        'scaffolding': 'development/SCAFFOLDING_GUIDE.md',
    }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help about the help system (meta!)."""
        return {
            'name': 'help',
            'description': (
                'Explore reveal help system - '
                'discover adapters, read guides'
            ),
            'syntax': 'help://[topic]',
            'examples': [
                {
                    'uri': 'help://',
                    'description': 'List all available help topics'
                },
                {
                    'uri': 'help://ast',
                    'description': 'Learn about ast:// adapter (query code as database)'
                },
                {
                    'uri': 'help://env',
                    'description': 'Learn about env:// adapter (environment variables)'
                },
                {
                    'uri': 'help://adapters',
                    'description': 'List all URI adapters with descriptions'
                },
                {
                    'uri': 'help://python-guide',
                    'description': (
                        'Python adapter comprehensive guide '
                        '(multi-shot examples, LLM integration)'
                    )
                },
                {
                    'uri': 'help://agent',
                    'description': 'Comprehensive agent reference (~40K tokens, task-pattern recipes)'
                },
                {
                    'uri': 'help://tricks',
                    'description': 'Cool tricks and hidden features guide'
                },
                {
                    'uri': "help://search?search=<term>",
                    'description': 'Full-text search over guides/adapters/examples by your own phrasing'
                }
            ],
            'notes': [
                'Each adapter exposes its own help via get_help() method',
                'Static guides load from markdown files in reveal/docs/',
                (
                    'New adapters automatically appear in help:// '
                    'when they implement get_help()'
                ),
                (
                    'For agents: --agent-help dumps the full reference '
                    '(~40K tokens, task-pattern recipes)'
                )
            ],
            'see_also': [
                'reveal --agent-help - Comprehensive agent reference (~40K tokens)',
                'reveal --help - Raw flag and subcommand listing',
                'reveal --list-supported - Supported file types'
            ]
        }

    def __init__(self, resource: str = '', query: Optional[str] = None, **kwargs: Any):
        """Initialize help adapter.

        Args:
            resource: Specific help topic to display ('' = list all)
            query: Unused, accepted for canonical signature conformance.
        """
        self.topic = resource or None
        # Merge auto-discovered guides with manual STATIC_HELP entries
        # STATIC_HELP takes precedence (allows aliases and special mappings)
        self.help_topics = self._discover_and_merge_guides()

    def _discover_and_merge_guides(self) -> Dict[str, GuideEntry]:
        """Auto-discover guide files, parse frontmatter, merge with STATIC_HELP.

        Discovery walks reveal/docs/ for *_GUIDE.md and *GUIDE.md files and
        derives a topic name from each filename. STATIC_HELP entries add extra
        topic names (aliases) for the same files and register non-*GUIDE.md
        docs (QUICK_START.md, AGENT_HELP.md, etc.) that auto-discovery misses.

        Metadata (description, category, token_estimate) is read from each
        file's frontmatter — never from a parallel Python dict. Aliases inherit
        their target file's metadata so adding `mcp-setup` and `mcp` for the
        same file does not double-list in the index.

        Returns:
            Dict mapping topic name → GuideEntry.
        """
        docs_dir = Path(__file__).parent.parent / 'docs'

        # Phase 1: parse frontmatter for every markdown file under docs/ once.
        # Aliases will look up metadata by relative file path.
        metadata_by_file: Dict[str, Dict[str, str]] = {}
        if docs_dir.exists():
            for md in docs_dir.rglob('*.md'):
                rel = md.relative_to(docs_dir).as_posix()
                metadata_by_file[rel] = _read_help_frontmatter(md)

        def _build(topic: str, file: str) -> GuideEntry:
            fm = metadata_by_file.get(file, {})
            # If frontmatter declares a canonical topic, only that topic is
            # categorized (and therefore listed in the index). Other topics
            # for the same file stay reachable but uncategorized.
            canonical = fm.get('help_topic', '')
            category = fm.get('help_category', '')
            if canonical and topic != canonical:
                category = ''
            return GuideEntry(
                topic=topic,
                file=file,
                description=fm.get('help_description', ''),
                category=category,
                token_estimate=fm.get('help_token_estimate', ''),
            )

        # Phase 2: auto-discover canonical topics from *_GUIDE.md / *GUIDE.md.
        discovered: Dict[str, GuideEntry] = {}
        if docs_dir.exists():
            # AST_ADAPTER_GUIDE.md -> 'ast-adapter'; QUERY_SYNTAX_GUIDE.md -> 'query-syntax'
            for guide in docs_dir.rglob('*_GUIDE.md'):
                topic = guide.stem.lower().replace('_guide', '').replace('_', '-')
                rel = guide.relative_to(docs_dir).as_posix()
                discovered[topic] = _build(topic, rel)

            # Catch any *GUIDE.md without the underscore separator (e.g. HTMLGUIDE.md).
            seen_files = {e.file for e in discovered.values()}
            for guide in docs_dir.rglob('*GUIDE.md'):
                rel = guide.relative_to(docs_dir).as_posix()
                if rel in seen_files:
                    continue
                topic = guide.stem.lower().replace('guide', '').replace('_', '-').strip('-')
                if topic:
                    discovered[topic] = _build(topic, rel)

        # Phase 3: merge STATIC_HELP. STATIC_HELP takes precedence — it provides
        # friendly topic names (e.g. 'ast' overrides discovered 'ast-adapter'),
        # explicit aliases ('config' → CONFIGURATION_GUIDE.md), and registers
        # non-*GUIDE.md docs (QUICK_START.md, AGENT_HELP.md, etc.).
        merged = dict(discovered)
        for topic, file in self.STATIC_HELP.items():
            merged[topic] = _build(topic, file)

        # Phase 4 (BACK-931): mark every topic but one canonical per file as an
        # alias. Prefer the topic with a non-empty category — that's already
        # the frontmatter-declared `help_topic` winner (e.g. 'tricks' over
        # 'recipes', 'subcommands' over 'dev'/'health'/'pack'/'review').
        # Files with no help_topic frontmatter at all (most auto-discovered
        # *_GUIDE.md doubles, e.g. 'ast' vs 'ast-adapter') leave every topic
        # uncategorized, so fall back to the shortest name — the same
        # friendly-name convention Phase 3's comment already describes.
        topics_by_file: Dict[str, List[str]] = {}
        for topic, entry in merged.items():
            topics_by_file.setdefault(entry.file, []).append(topic)
        for file, topics in topics_by_file.items():
            if len(topics) <= 1:
                continue
            categorized = [t for t in topics if merged[t].category]
            canonical = categorized[0] if len(categorized) == 1 else min(topics, key=lambda t: (len(t), t))
            for t in topics:
                if t != canonical:
                    merged[t] = replace(merged[t], is_alias=True)

        return merged

    def _indexed_static_guides(self) -> List[Dict[str, str]]:
        """The static_guides list as shown on the help:// index: one entry per
        guide FILE, not per topic (BACK-999).

        self.help_topics has ~110 entries because every alias (mcp-setup,
        quick-start, ...) and every adapter guide (already listed separately
        under 'adapters') gets its own topic key. The text renderer has always
        deduped this down to ~33 index-worthy entries by file path, keeping
        the shortest topic name per file and dropping category='' (adapter
        guide) entries — but that dedup lived only in the renderer, so the
        JSON 'static_guides' field shipped all ~110 undeduped entries, nearly
        doubling help:// --format=json for no informational gain (measured:
        19.2KB of the 33KB total, ~2x the ~10.7KB a deduped list costs).
        Moving the dedup here means text and JSON agree on what the index is.
        """
        best_by_file: Dict[str, GuideEntry] = {}
        for entry in self.help_topics.values():
            if not entry.category:
                continue
            existing = best_by_file.get(entry.file)
            if existing is None or len(entry.topic) < len(existing.topic):
                best_by_file[entry.file] = entry
        return [
            e.to_dict() for e in
            sorted(best_by_file.values(), key=lambda e: e.topic)
        ]

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get help structure (list of available topics)."""
        return ResultBuilder.create(
            result_type='help',
            source='help://',
            source_type='runtime',
            contract_version=CONTRACT_VERSION,
            data={
                'available_topics': self._list_topics(),
                'adapters': self._list_adapters(),
                # Each entry: {topic, file, description, category, token_estimate}.
                # The renderer reads category/description/token_estimate from here;
                # there is no parallel dict in the renderer module. Deduped to
                # one entry per file (see _indexed_static_guides) — the full
                # alias-inclusive map is self.help_topics, used for per-topic
                # lookups, not for this listing.
                'static_guides': self._indexed_static_guides(),
            }
        )

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get help for a specific topic.

        Args:
            element_name: Topic name (adapter scheme, 'adapters', 'agent', etc.)
                   Can also be 'adapter/section' for section extraction
                   Or 'schemas/adapter' for machine-readable schemas
                   Or 'examples/task' for canonical query recipes

        Returns:
            Help content dict or None if not found
        """
        result = self._get_element_impl(element_name, **kwargs)
        # Every tier hand-rolls its own dict below; get_structure() is the only
        # one that stamps contract_version on its own (BACK-696). Stamp it here,
        # once, rather than touching every builder above.
        if isinstance(result, dict):
            result.setdefault('contract_version', '1.1')
        return result

    def _get_element_impl(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        topic = element_name  # Alias for readability
        # Check for schemas route: help://schemas/ssl
        # Bare 'schemas/' lists available adapters
        if topic == 'schemas' or topic == 'schemas/':
            # Only list adapters that actually provide a schema — listing a
            # meta-adapter (e.g. help://) that returns None would walk an agent
            # straight into a "no schema available" error from its own menu (N1).
            adapters = self._adapters_with_schema()
            return {
                'type': 'adapter_schema',
                'adapter': '',
                'error': 'No adapter specified',
                'available_adapters': adapters,
                'usage': 'reveal help://schemas/<adapter>',
                'examples': [
                    'reveal help://schemas/ast',
                    'reveal help://schemas/ssl',
                    'reveal help://schemas/git',
                ],
                # BACK-847: help://schema (singular) is a different page — the
                # markdown front-matter validation guide — not an alias/typo of
                # this one. Cross-signpost so landing here doesn't silently
                # misinform an agent looking for that guide instead.
                'note': (
                    'Looking for markdown front-matter validation instead? '
                    'That is help://schema (singular) — this page is adapter '
                    'query schemas (plural).'
                ),
                'next': [
                    'reveal help://schemas/index',
                    'reveal help://schemas/all',
                ],
            }
        # Full-text search over the help corpus: help://search?search=<term>
        # (also accepts help://search/<term> for shells that mangle '?'). Param
        # name matches the ?search= convention already used by claude://,
        # codex://, and xlsx:// for the same "free-text content search"
        # operation (see QUERY_PARAMETER_REFERENCE.md's Search vs Filter note).
        if topic == 'search' or topic.startswith('search?') or topic.startswith('search/'):
            if topic.startswith('search?'):
                from urllib.parse import parse_qs
                params = parse_qs(topic.split('?', 1)[1])
                query_term = (params.get('search') or [''])[0]
            elif topic.startswith('search/'):
                query_term = topic.split('/', 1)[1]
            else:
                query_term = ''
            return self._search_help(query_term)
        if topic in ('rules', 'rules/'):
            # BACK-846: --rules was flag-only, so MCP clients (whose only
            # introspection channel is reveal_query(uri)) could not reach the
            # rule catalog at all.
            return self._get_rules_catalog()
        if topic in ('languages', 'languages/'):
            # BACK-846: same hole for --languages.
            return self._get_languages_catalog()
        if topic in ('schemas/all', 'schemas/index'):
            # BACK-840: the aggregate view agents kept asking for already
            # exists as `reveal --discover` (flag-only, invisible from the
            # URI tier); route it here instead of building a second one.
            # 'index' is the ~1K thin rung (scheme/uri_syntax/description
            # only) between the bare menu and the full 'all' payload.
            return self._get_schema_all(thin=(topic == 'schemas/index'))
        if topic.startswith('schemas/'):
            remainder = topic.split('/', 1)[1]
            # help://schemas/<adapter>/<output_type> drills into one output type;
            # help://schemas/<adapter>/full returns the unsummarized payload.
            if '/' in remainder:
                adapter_name, section = remainder.split('/', 1)
                return self._get_adapter_schema(adapter_name, section=section)
            return self._get_adapter_schema(remainder)

        # Check for examples route: help://examples/security
        # Bare 'examples' and 'examples/' show the task list (same as passing empty task)
        if topic == 'examples' or topic == 'examples/':
            return self._get_example_recipes('')
        if topic.startswith('examples/'):
            task_name = topic.split('/', 1)[1]
            return self._get_example_recipes(task_name)

        # Check for section extraction: help://ast/workflows or help://ast/full
        if '/' in topic:
            adapter_name, uri_section = topic.split('/', 1)
            # Static guides support /full to bypass progressive disclosure
            if adapter_name in self.help_topics:
                if uri_section == 'full':
                    heading_filter = kwargs.get('section')
                    result = self._load_static_help(adapter_name, full=True, section=heading_filter)
                    if result and 'error' not in result:
                        result['topic'] = f'{adapter_name}/full'
                    return result
                # Fall through: if also a URI adapter, let it handle the section
            # Only route to adapter section handler when the adapter actually exists;
            # returning None here gives a clean "not found" rather than a misleading
            # "Unknown section" error when the base topic doesn't exist at all.
            if adapter_name in _ADAPTER_REGISTRY:
                return self._get_adapter_section(adapter_name, uri_section)
            return None

        # Quick-start orientation cheat sheet
        if topic == 'quick':
            return self._get_quick_help()

        # Adapter ecosystem relationships map
        if topic == 'relationships':
            return self._get_adapter_relationships()

        # Anti-patterns: extract bounded section from AGENT_HELP rather than dumping full doc
        if topic == 'anti-patterns':
            return self._get_anti_patterns_section()

        # Check if it's a static guide (includes auto-discovered + manual)
        if topic in self.help_topics:
            return self._load_static_help(topic, section=kwargs.get('section'))

        # Check if it's 'adapters' (list all)
        if topic == 'adapters':
            return self._get_all_adapter_help()

        # Check if it's an adapter scheme
        if topic in _ADAPTER_REGISTRY:
            return self._get_adapter_help(topic)

        # Check if it's a known file-based analyzer (not a URI adapter)
        # Return focused inline help rather than failing with "not found"
        file_analyzer_help = self._get_file_analyzer_help(topic)
        if file_analyzer_help is not None:
            return file_analyzer_help

        return None

    def _validate_section_name(
        self, adapter_name: str, section: str
    ) -> Optional[Dict[str, Any]]:
        """Validate section name is valid.

        Returns:
            Error dict if invalid, None if valid
        """
        if section not in self.VALID_SECTIONS:
            valid_sections = ', '.join(sorted(self.VALID_SECTIONS))
            return {
                'type': 'help_section',
                'adapter': adapter_name,
                'section': section,
                'error': 'Invalid section',
                'message': (
                    f"Unknown section '{section}'. "
                    f"Valid sections: {valid_sections}"
                ),
                'next': [f'reveal help://{adapter_name}'],
            }
        return None

    def _validate_adapter_exists(
        self, adapter_name: str, section: str
    ) -> Optional[Dict[str, Any]]:
        """Validate adapter exists in registry.

        Returns:
            Error dict if not found, None if exists
        """
        if adapter_name not in _ADAPTER_REGISTRY:
            return {
                'type': 'help_section',
                'adapter': adapter_name,
                'section': section,
                'error': 'Unknown adapter',
                'message': f"No adapter named '{adapter_name}'",
                'next': ['reveal help://adapters'],
            }
        return None

    def _extract_section_content(
        self, adapter_name: str, section: str, help_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract specific section from adapter help.

        Returns:
            Section content dict or error dict
        """
        # Map section names to help dict keys
        section_key_map = {
            'workflows': 'workflows',
            'try-now': 'try_now',
            'anti-patterns': 'anti_patterns',
        }

        key = section_key_map.get(section)
        content = help_data.get(key) if key else None

        if not content:
            return {
                'type': 'help_section',
                'adapter': adapter_name,
                'section': section,
                'error': 'Section not found',
                'message': (
                    f"Adapter '{adapter_name}' does not have "
                    f"a '{section}' section"
                ),
                'next': [f'reveal help://{adapter_name}'],
            }

        return {
            'type': 'help_section',
            'adapter': adapter_name,
            'section': section,
            'content': content
        }

    def _get_adapter_section(
        self, adapter_name: str, section: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific section from an adapter's help.

        Args:
            adapter_name: Adapter scheme name (e.g., 'ast')
            section: Section name (e.g., 'workflows', 'try-now')

        Returns:
            Dict with section content or error
        """
        # Validate section name
        error = self._validate_section_name(adapter_name, section)
        if error:
            return error

        # Validate adapter exists
        error = self._validate_adapter_exists(adapter_name, section)
        if error:
            return error

        # Get full adapter help
        help_data = self._get_adapter_help(adapter_name)
        if not help_data or 'error' in help_data:
            return help_data

        # Extract and return section content
        return self._extract_section_content(adapter_name, section, help_data)

    def _list_topics(self) -> List[str]:
        """List all available help topics."""
        topics: List[str] = []

        # Add adapter schemes
        topics.extend(_ADAPTER_REGISTRY.keys())

        # Add meta topics
        topics.append('adapters')

        # Add static guides (auto-discovered + manual)
        topics.extend(self.help_topics.keys())

        # Adapter schemes and STATIC_HELP aliases legitimately overlap by
        # design (e.g. 'ast' names both the adapter and its friendly guide
        # alias) — dedupe the combined list rather than the source dicts.
        return sorted(set(topics))

    # Discovery entry points that aren't adapter schemes or static guides but are
    # valid help:// topics — included when suggesting fixes for a mistyped topic.
    _DISCOVERY_TOPICS = (
        'quick', 'relationships', 'anti-patterns', 'schemas', 'examples',
        'rules', 'languages', 'search',
    )

    def suggest_topics(self, query: str, n: int = 3) -> List[str]:
        """Closest known help topics to a mistyped `query`, best first.

        Used by the CLI to route a lost agent back into discovery instead of
        dead-ending on an unknown topic (BACK-692). Matches against the full
        topic universe — adapter schemes, static guides, and discovery routes.
        """
        import difflib

        # Compare against the base topic only (before any '/section').
        base = query.split('/', 1)[0]
        universe = set(self._list_topics()) | set(self._DISCOVERY_TOPICS)
        return difflib.get_close_matches(base, sorted(universe), n=n, cutoff=0.6)

    def _search_help(self, query_term: str) -> Dict[str, Any]:
        """Full-text search over reveal's own help corpus (help://search?search=<term>).

        BACK-1023: help://quick's decision_tree only routes a reader who
        already matches its curated phrasing ("find dead code" hits
        calls://, but "find callers" -- same underlying answer -- doesn't
        match any row). This searches topic/description/content across
        static guides, adapter descriptions, and help://examples recipes so
        an agent can query its own intent instead of depending on a human
        having pre-curated every phrasing.
        """
        term = (query_term or '').strip()
        if not term:
            return {
                'type': 'help_search',
                'query': '',
                'error': 'No search term',
                'message': "Usage: reveal 'help://search?search=<term>'",
                'examples': [
                    "reveal 'help://search?search=find callers'",
                    "reveal 'help://search?search=dead code'",
                ],
            }

        # Word-order/pluralization-tolerant matching: every query word must
        # appear as a substring *somewhere* in the haystack, not as one
        # contiguous phrase -- e.g. "tests coverage" and "test coverage" both
        # match a haystack containing "test coverage" or "coverage of tests".
        # Same convention Beth's explore already uses (see CLAUDE.md), for
        # the same reason: an agent's phrasing rarely matches curated text
        # word-for-word.
        tokens = term.lower().split()

        def _matches(haystack: str) -> bool:
            h = haystack.lower()
            return all(tok in h for tok in tokens)

        # Each hit gets a strength: 2 = query matched the item's own name/id,
        # 1 = matched its short description/metadata, 0 = matched only deep
        # in guide content. Adapters rank above guides at equal strength --
        # "here's the tool" is usually the more actionable answer than
        # "here's a doc that happens to mention it".
        _TYPE_PRIORITY = {'adapter': 0, 'guide': 1, 'recipe': 2}
        hits: List[Dict[str, Any]] = []
        docs_root = Path(__file__).parent.parent / 'docs'

        # Adapters: scheme name + description.
        for adapter in self._list_adapters():
            scheme = adapter['scheme']
            description = adapter.get('description', '')
            strength = 2 if _matches(scheme) else (1 if _matches(f"{scheme} {description}") else None)
            if strength is not None:
                hits.append({
                    'type': 'adapter',
                    'scheme': scheme,
                    'snippet': description or scheme,
                    'command': f'reveal help://{scheme}',
                    '_strength': strength,
                })

        # Static guides: topic/description match first (cheap); fall back to
        # a content grep for a snippet when the terms aren't in the metadata.
        for guide in self._indexed_static_guides():
            topic = guide['topic']
            description = guide.get('description', '')
            snippet: Optional[str] = None
            strength = 0
            if _matches(topic):
                snippet, strength = description or topic, 2
            elif _matches(f"{topic} {description}"):
                snippet, strength = description or topic, 1
            else:
                try:
                    content = (docs_root / guide['file']).read_text(encoding='utf-8')
                except OSError:
                    content = ''
                for line in content.splitlines():
                    if _matches(line):
                        snippet = line.strip()
                        break
            if snippet is not None:
                hits.append({
                    'type': 'guide',
                    'topic': topic,
                    'snippet': snippet[:200],
                    'command': f'reveal help://{topic}',
                    '_strength': strength,
                })

        # help://examples recipes: task name, task description, or any one
        # recipe's goal/description within it.
        for task, recipe_set in _EXAMPLE_RECIPES.items():
            matched_goal = None
            strength = 0
            if _matches(task):
                strength = 2
            elif _matches(f"{task} {recipe_set.get('description', '')}"):
                strength = 1
            else:
                for recipe in recipe_set.get('recipes', []):
                    combined = f"{recipe.get('goal', '')} {recipe.get('description', '')}"
                    if _matches(combined):
                        matched_goal = recipe.get('goal')
                        break
                if matched_goal is None:
                    continue
            hits.append({
                'type': 'recipe',
                'task': task,
                'snippet': matched_goal or recipe_set.get('description', task),
                'command': f'reveal help://examples/{task}',
                '_strength': strength,
            })

        hits.sort(key=lambda h: (-h.pop('_strength'), _TYPE_PRIORITY.get(h['type'], 9)))
        hits = hits[:20]

        return {
            'type': 'help_search',
            'query': term,
            'count': len(hits),
            'hits': hits,
            'next': (
                [h['command'] for h in hits[:3]] if hits
                else ['reveal help://quick', 'reveal help://adapters']
            ),
        }

    def _get_adapter_description(self, adapter_class: type[Any]) -> str:
        """Get description from adapter's help method.

        Args:
            adapter_class: Adapter class

        Returns:
            Description string or empty string if unavailable
        """
        try:
            help_data = adapter_class.get_help()
            if help_data:
                return str(help_data.get('description', ''))
        except Exception:
            # If get_help() fails, return empty
            pass
        return ''

    def _list_adapters(self) -> List[Dict[str, Any]]:
        """List all registered adapters with basic info."""
        adapters = []
        for scheme, adapter_class in _ADAPTER_REGISTRY.items():
            if scheme in self._INTERNAL_ADAPTERS:
                continue
            has_help = (
                hasattr(adapter_class, 'get_help') and
                callable(getattr(adapter_class, 'get_help'))
            )

            info = {
                'scheme': scheme,
                'class': adapter_class.__name__,
                'has_help': has_help
            }

            # Add description if available
            if has_help:
                info['description'] = self._get_adapter_description(adapter_class)

            adapters.append(info)

        return sorted(adapters, key=lambda x: x['scheme'])

    def _get_file_analyzer_help(self, topic: str) -> Optional[Dict[str, Any]]:
        """Return inline help for file-based analyzers (not URI adapters).

        These are not in _ADAPTER_REGISTRY but users sometimes try `reveal help://nginx`
        thinking it's a URI scheme. Return focused usage help rather than "not found".
        """
        FILE_ANALYZERS: Dict[str, Dict[str, Any]] = {
            'nginx': {
                'name': 'nginx',
                'type': 'file_analyzer',
                'description': 'nginx is a file-based analyzer — pass a config file path directly',
                'note': (
                    'nginx is a file-based analyzer — pass config file paths directly. '
                    'The nginx:// URI scheme is not yet implemented.'
                ),
                'examples': [
                    {'uri': 'reveal /etc/nginx/nginx.conf', 'description': 'See all server blocks'},
                    {'uri': 'reveal /etc/nginx/nginx.conf --check', 'description': 'Run N001-N007 rules'},
                    {'uri': 'reveal /etc/nginx/conf.d/example.com.conf --check', 'description': 'Check a single vhost'},
                ],
                'cli_flags': [
                    '--check                      # Run N001-N007 nginx quality rules',
                    '--diagnose                   # Audit nginx error log for ACME/SSL failures',
                    '--check-acl                  # Verify nginx ACL configuration',
                    '--validate-nginx-acme        # Validate ACME challenge paths',
                    '--check-conflicts            # Detect conflicting server_name directives',
                    '--log-path PATH              # Override error log path for --diagnose',
                    '--dns-verified               # Skip DNS check (use when DNS is verified)',
                    '--extract domains|certs|...  # Extract specific elements (domains, certs, paths)',
                ],
                'see_also': [
                    'reveal help://ssl - SSL certificate inspection',
                    'reveal help://cpanel - cPanel user environment adapter',
                ],
            },
        }
        return FILE_ANALYZERS.get(topic)

    def _get_adapter_help(self, scheme: str) -> Optional[Dict[str, Any]]:
        """Get help for a specific adapter.

        Args:
            scheme: Adapter scheme name

        Returns:
            Help dict or None if adapter has no help
        """
        adapter_class: Optional[type[Any]] = _ADAPTER_REGISTRY.get(scheme)
        if not adapter_class:
            return None

        if not hasattr(adapter_class, 'get_help'):
            return {
                'scheme': scheme,
                'error': 'No help available',
                'message': (
                    f'{adapter_class.__name__} does not provide '
                    f'help documentation'
                ),
                'next': ['reveal help://adapters'],
            }

        try:
            help_data = adapter_class.get_help()
            if help_data:
                help_data['scheme'] = scheme  # Ensure scheme is included
                self._add_related_next(help_data, scheme)
            return help_data  # type: ignore[no-any-return]
        except Exception as e:
            return {
                'scheme': scheme,
                'error': 'Help generation failed',
                'message': str(e),
                'next': ['reveal help://adapters'],
            }

    def _related_adapters(self, scheme: str) -> List[str]:
        """Derive related-adapter pointers for `scheme` from `_get_adapter_relationships()`.

        BACK-926: replaces the old hand-maintained `related` dict in
        `_render_help_breadcrumbs`, which drifted from this data (the only
        mechanism with a registry-completeness test) and reached 1 of 25
        adapters in practice. Treats each curated pair as undirected so both
        adapters in a pair point at each other.
        """
        neighbors: Dict[str, List[str]] = {}
        for cluster in self._get_adapter_relationships()['clusters']:
            for a, b, _rationale in cluster['pairs']:
                for x, y in ((a, b), (b, a)):
                    bucket = neighbors.setdefault(x, [])
                    if y not in bucket:
                        bucket.append(y)
        return [f'reveal help://{s}' for s in neighbors.get(scheme, [])[:2]]

    def _add_related_next(self, data: Dict[str, Any], scheme: str) -> None:
        """Append `_related_adapters(scheme)` pointers onto `data['next']` in place."""
        related = self._related_adapters(scheme)
        if not related:
            return
        existing = data.setdefault('next', [])
        for pointer in related:
            if pointer not in existing:
                existing.append(pointer)

    def _add_related_see_also(self, data: Dict[str, Any], topic: str) -> None:
        """BACK-936: surface the adapter's `get_help()['see_also']` on a guide.

        `help://<scheme>` resolves to the static guide (this branch) before
        the adapter-scheme branch ever runs, so for the 23 of 24 schemes with
        a same-named guide, `get_help()`'s `see_also` was otherwise dead data
        with no reachable route at all. No-op for meta guides (tricks,
        schema, ...) that aren't adapter scheme names.
        """
        adapter_class = _ADAPTER_REGISTRY.get(topic)
        if not adapter_class or not hasattr(adapter_class, 'get_help'):
            return
        try:
            adapter_help = adapter_class.get_help()
        except Exception:
            return
        see_also = adapter_help.get('see_also') if adapter_help else None
        if see_also:
            data['see_also'] = see_also

    # Rank hints for help://quick's top command block. Lower sorts first;
    # unranked adapters (including project-local plugins) default to 100 and
    # sort alphabetically after every ranked one. This is the "intent contract"
    # M4 in AGENT_CLI_ONBOARDING_STRATEGY_2026-07-01.md asked for: adapters
    # already carry a one-line description + starter query via get_help(),
    # this dict only decides *priority*, not content — so the command list
    # can't drift from the registry, and new adapters are never missing.
    _QUICK_RANK: Dict[str, int] = {
        'ast': 0,
        'calls': 1,
        'stats': 2,
        'claude': 3,
        'git': 4,
        'ssl': 5,
        'domain': 6,
        'nginx': 7,
        'sqlite': 8,
        'cpanel': 9,
    }
    _QUICK_COMMAND_COUNT = 10

    def _get_quick_commands(self) -> List[Dict[str, str]]:
        """Derive the top command block from the adapter registry.

        Two synthetic file-navigation entries lead (reveal isn't only URI
        adapters) followed by the highest-ranked registered adapters, each
        represented by its own get_help() description + first example.
        """
        commands = [
            {
                'cmd': 'reveal <file.py>',
                'description': 'Outline a Python/JS/Go/etc. file — functions, classes, imports',
            },
            {
                'cmd': 'reveal <dir/>',
                'description': 'Directory tree with file sizes and types',
            },
        ]

        candidates = []
        for scheme, adapter_class in _ADAPTER_REGISTRY.items():
            if scheme in self._INTERNAL_ADAPTERS or scheme == 'help':
                continue
            help_data = self._get_adapter_help(scheme)
            if not help_data or 'error' in help_data:
                continue
            examples = help_data.get('examples') or []
            uri = examples[0].get('uri', '') if examples else ''
            description = help_data.get('description', '')
            if not uri or not description:
                continue
            rank = self._QUICK_RANK.get(scheme, 100)
            candidates.append((rank, scheme, uri, description))

        candidates.sort(key=lambda c: (c[0], c[1]))
        # -1 reserves a slot for the trailing help://adapters pointer below.
        slots = max(self._QUICK_COMMAND_COUNT - len(commands) - 1, 0)
        for _rank, _scheme, uri, description in candidates[:slots]:
            commands.append({'cmd': f'reveal {uri}', 'description': description})

        commands.append({
            'cmd': 'reveal help://adapters',
            'description': 'List all adapters with syntax and examples',
        })
        return commands

    def _get_quick_help(self) -> Dict[str, Any]:
        """Return a concise orientation cheat-sheet (help://quick)."""
        return {
            'type': 'help_quick',
            'title': 'Reveal — Quick Reference',
            'commands': self._get_quick_commands(),
            'decision_tree': [
                {'want': 'understand code structure (functions, classes, complexity)',
                 'use': 'ast://', 'example': "reveal ast://src/?complexity>10"},
                {'want': 'know who calls what / find dead code',
                 'use': 'calls://', 'example': "reveal 'calls://src/?target=my_fn'"},
                {'want': 'search text or an identifier across many files (with enclosing-function context)',
                 'use': '--grep', 'example': "reveal src/ --grep 'API_TIMEOUT'"},
                {'want': 'check import health / circular deps',
                 'use': 'imports://', 'example': "reveal imports://src/"},
                {'want': 'compare files or git revisions',
                 'use': 'diff://', 'example': "reveal diff://git://HEAD~1/.:git://HEAD/."},
                {'want': 'SSL/TLS certificate status',
                 'use': 'ssl://', 'example': "reveal ssl://example.com --check"},
                {'want': 'full server audit (SSL + ACL + nginx)',
                 'use': 'cpanel://', 'example': "reveal cpanel://USER/full-audit"},
                {'want': 'nginx vhost config and health',
                 'use': 'nginx://', 'example': "reveal nginx://example.com"},
                {'want': 'domain DNS / WHOIS / email health',
                 'use': 'domain://', 'example': "reveal domain://example.com"},
                {'want': 'search git commit history by message, author, or date',
                 'use': 'git://', 'example': "reveal 'git://.?message~=fix'"},
                {'want': 'search markdown docs or notes by content',
                 'use': 'markdown://', 'example': "reveal docs/ --grep 'keyword'"},
                {'want': 'inspect a SQLite, MySQL database, or Excel workbook',
                 'use': 'sqlite:// / mysql:// / xlsx://', 'example': "reveal sqlite:///path/to/app.db"},
                {'want': 'inspect environment variables or Python runtime',
                 'use': 'env:// / python://', 'example': "reveal env://"},
                {'want': 'search prior Claude sessions by topic or project',
                 'use': 'claude://', 'example': "reveal 'claude://sessions/?search=auth-refactor' --format=json"},
                {'want': 'review a session as prompt/answer pairs, not raw messages',
                 'use': 'claude://.../exchanges', 'example': "reveal claude://session/my-session/exchanges"},
                {'want': 'search OpenAI Codex CLI sessions by content (or ?filter= by title)',
                 'use': 'codex://', 'example': "reveal 'codex://sessions/?search=auth-refactor'"},
                {'want': 'discover live project-specific adapters',
                 'use': 'help://adapters', 'example': "reveal help://adapters"},
            ],
            'next_steps': [
                'reveal help://adapters          # full adapter list',
                'reveal help://ast               # Python/JS/Go AST queries',
                'reveal help://ssl               # TLS cert adapter guide',
                'reveal help://examples          # browse all task-based query recipes',
                'reveal help://examples/security # security query recipes',
                'reveal help://agent             # AI agent usage guide',
                'reveal help://schemas/index     # thin index of every adapter schema (~1K tokens)',
                'reveal help://schemas/all       # full machine-readable schema for every adapter (~10K tokens)',
                'reveal help://rules             # pattern-detection rule catalog',
                'reveal help://languages         # supported languages + analyzer depth',
                'reveal help://output-diagnostics # --format vs meta trust envelope vs --provenance vs --perf',
                "reveal 'help://search?search=<term>' # full-text search when nothing above matches your phrasing",
            ],
        }

    def _get_adapter_relationships(self) -> Dict[str, Any]:
        """Return the adapter ecosystem map (help://relationships)."""
        return {
            'type': 'help_relationships',
            'title': 'Reveal Adapter Ecosystem',
            'clusters': [
                {
                    'name': 'Code Analysis',
                    'adapters': ['ast', 'calls', 'diff', 'stats', 'imports', 'depends', 'git', 'patches', 'surface', 'contracts', 'hotspots', 'deps', 'architecture', 'overview', 'testability', 'trace', 'pack'],
                    'pairs': [
                        ('ast', 'calls', 'structure feeds call-graph queries'),
                        ('ast', 'diff', 'compare element complexity across versions'),
                        ('ast', 'stats', 'same code, different lens: quality metrics'),
                        ('ast', 'imports', 'structure + dependency graph'),
                        ('calls', 'diff', 'impact analysis: who calls what changed'),
                        ('patches', 'ast', 'test churn pressure on specific functions'),
                        ('patches', 'calls', 'highest-churn tests + call-graph identifies blast radius'),
                        ('imports', 'depends', 'forward imports + reverse dependency graph'),
                        ('stats', 'git', 'quality score over commit history'),
                        ('git', 'diff', 'git history drives structural diff views'),
                        ('surface', 'imports', 'external boundaries + what imports reach them'),
                        ('surface', 'stats', 'attack-surface map + quality score for the same tree'),
                        ('contracts', 'ast', 'architectural seams + full structure for the same classes'),
                        ('contracts', 'calls', 'contracts + who calls into their implementations'),
                        ('hotspots', 'stats', 'ranked hotspot list draws on the same quality score'),
                        ('hotspots', 'ast', 'function-level complexity ranking feeds the hotspot list'),
                        ('deps', 'imports', 'dependency dashboard is composed entirely from imports:// queries'),
                        ('architecture', 'imports', 'entry points/core abstractions/cycles feed the architecture brief'),
                        ('architecture', 'ast', 'complexity ranking feeds the high-complexity-entry risk'),
                        ('overview', 'stats', 'dashboard hotspots/quality pulse draw on the same quality score'),
                        ('overview', 'git', 'recent-activity section is a git:// log query'),
                        ('testability', 'patches', 'testability joins the same patch scan against production boundary fan-out'),
                        ('trace', 'calls', 'trace narrative is built on calls:// BFS machinery'),
                        ('pack', 'imports', '--architecture/--focus ranking is built on the same import/dependency graph'),
                    ],
                },
                {
                    'name': 'Infrastructure',
                    'adapters': ['nginx', 'ssl', 'letsencrypt', 'domain', 'cpanel', 'autossl'],
                    'pairs': [
                        ('nginx', 'ssl', 'validate certs referenced in nginx configs'),
                        ('nginx', 'domain', 'DNS health for domains in nginx configs'),
                        ('ssl', 'domain', 'cert chain + DNS/WHOIS in one pass'),
                        ('ssl', 'letsencrypt', 'on-disk cert details for Let\'s Encrypt live certs'),
                        ('cpanel', 'ssl', 'per-user cert inventory and health'),
                        ('cpanel', 'autossl', 'AutoSSL run logs for cPanel users'),
                        ('cpanel', 'nginx', 'nginx vhost config for this cPanel user'),
                        ('letsencrypt', 'nginx', 'cross-reference certbot certs with nginx vhosts'),
                    ],
                },
                {
                    'name': 'Data & Config',
                    'adapters': ['sqlite', 'mysql', 'json', 'env', 'xlsx'],
                    'pairs': [
                        ('sqlite', 'mysql', 'same query API, two database backends'),
                        ('json', 'sqlite', 'inspect app state: exported JSON or live DB'),
                        ('env', 'python', 'runtime environment + live module introspection'),
                        ('xlsx', 'sqlite', 'tabular data inspection across formats'),
                        ('xlsx', 'json', 'structured data: Excel vs JSON'),
                    ],
                },
                {
                    'name': 'Sessions & Docs',
                    'adapters': ['claude', 'codex', 'git', 'markdown'],
                    'pairs': [
                        ('claude', 'git', 'cross-reference session work with code changes'),
                        ('codex', 'claude', 'OpenAI Codex vs Claude Code session analysis'),
                        ('claude', 'markdown', 'session docs and knowledge base'),
                        ('markdown', 'git', 'doc history and authorship'),
                    ],
                },
                {
                    'name': 'Self-Describing',
                    'adapters': ['help', 'reveal', 'python', 'ast'],
                    'pairs': [
                        ('help', 'reveal', 'help:// documents it; reveal:// introspects it'),
                        ('reveal', 'ast', 'reveal uses ast:// to analyze itself'),
                        ('python', 'ast', 'runtime introspection vs static analysis'),
                    ],
                },
            ],
            'power_pairs': [
                {
                    'adapters': ['ast', 'calls'],
                    'description': 'Core code understanding: structure + relationships',
                    'example': "reveal src/auth.py  &&  reveal 'calls://src/?target=validate_token'",
                },
                {
                    'adapters': ['diff', 'stats'],
                    'description': 'PR review: what changed + quality impact',
                    'example': "reveal pack src/ --since main --content  &&  reveal 'ast://src/?complexity>10'",
                },
                {
                    'adapters': ['nginx', 'ssl'],
                    'description': 'Infrastructure audit: config + cert validation',
                    'example': "reveal nginx://example.com  &&  reveal ssl://example.com --check",
                },
                {
                    'adapters': ['sqlite', 'mysql'],
                    'description': 'Portable DB inspection: same syntax, two backends',
                    'example': "reveal sqlite:///dev.db/users  →  reveal mysql://prod/users",
                },
                {
                    'adapters': ['claude', 'git'],
                    'description': 'Session archaeology: history + code changes',
                    'example': "reveal 'claude://sessions/?search=auth'  &&  reveal 'git://src/?message~=auth'",
                },
            ],
        }

    def _get_anti_patterns_section(self) -> Optional[Dict[str, Any]]:
        """Extract the Common Mistakes section from AGENT_HELP.md.

        Returns a bounded, focused result rather than the full 4K-line guide.
        Use help://agent for the complete guide.
        """
        help_path = Path(__file__).parent.parent / 'docs' / 'AGENT_HELP.md'
        try:
            lines = help_path.read_text(encoding='utf-8').splitlines()
        except Exception:
            return None

        # Find the section and extract until the next ## heading
        start = None
        for i, line in enumerate(lines):
            if line.startswith('## Common Mistakes'):
                start = i
                break
        if start is None:
            return None

        section_lines = []
        for line in lines[start:]:
            if section_lines and line.startswith('## '):
                break
            section_lines.append(line)

        return {
            'type': 'static_help',
            'topic': 'anti-patterns',
            'file': 'AGENT_HELP.md',
            'content': '\n'.join(section_lines),
            'note': 'Extracted from AGENT_HELP.md — use help://agent for the complete guide.',
            # BACK-841: short enough never to truncate, so it never got the
            # '/full' footer that longer guides use as their onward pointer —
            # leaving it a measured dead end.
            'next': [
                'reveal help://agent',
                'reveal help://tricks',
                'reveal help://quick',
            ],
        }

    # Internal/scaffold adapters excluded from public listings
    _INTERNAL_ADAPTERS = {'demo', 'test'}

    def _get_all_adapter_help(self) -> Dict[str, Any]:
        """Get help for all adapters."""
        public_schemes = [s for s in _ADAPTER_REGISTRY.keys() if s not in self._INTERNAL_ADAPTERS]
        all_help: Dict[str, Any] = {
            'type': 'adapter_summary',
            'count': len(public_schemes),
            'adapters': {}
        }

        for scheme in public_schemes:
            help_data = self._get_adapter_help(scheme)
            if help_data and 'error' not in help_data:
                example = ''
                if help_data.get('examples'):
                    example = help_data.get('examples', [{}])[0].get('uri', '')

                all_help['adapters'][scheme] = {
                    'description': help_data.get('description', ''),
                    'syntax': help_data.get('syntax', ''),
                    'example': example
                }

        # BACK-841: this page was one of four measured dead ends — 6.4KB of
        # adapter names with no onward pointer. The obvious next questions are
        # "what can I query on one of these?" and "how do they combine?".
        all_help['next'] = [
            'reveal help://<adapter>',
            'reveal help://schemas/index',
            'reveal help://relationships',
        ]
        return all_help

    _PROGRESSIVE_DISCLOSURE_THRESHOLD = 200
    # Topics intentionally loaded in full go here. Empty by design: '--agent-help'
    # used to be exempted, dumping ~40K tokens against the tool's own progressive-
    # disclosure thesis; it now truncates like every other guide (reveal help://agent/full
    # for the complete manual).
    _FULL_ONLY_TOPICS: frozenset = frozenset()

    def _load_static_help(self, topic: str, full: bool = False,
                          section: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Load help from static markdown file.

        Args:
            topic: Topic name ('agent', 'intro', 'tricks', etc.)
            full: If True, bypass progressive disclosure and return the complete file.
            section: If provided, filter content to just the named heading and its body.

        Returns:
            Help content dict or None if file not found
        """
        entry = self.help_topics.get(topic)
        if not entry:
            return None
        filename = entry.file

        # Help files are in reveal/docs/ directory
        help_path = Path(__file__).parent.parent / 'docs' / filename

        try:
            with open(help_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Guides carry YAML front matter (title, help_* fields) consumed by
            # the topic registry; strip it so it never leaks into rendered help.
            content = _strip_frontmatter(content)
            lines = content.splitlines()

            if section:
                content = self._extract_markdown_section(lines, section, topic)
                if content is None:
                    return {
                        'type': 'static_guide',
                        'topic': topic,
                        'error': 'Section not found',
                        'message': (
                            f"Section '{section}' not found in {filename}.\n"
                            f"Tip: reveal help://{topic}/full | grep -i '<keyword>' to locate headings."
                        ),
                        'next': [f'reveal help://{topic}/full'],
                    }
            elif (not full and topic not in self._FULL_ONLY_TOPICS
                    and len(lines) > self._PROGRESSIVE_DISCLOSURE_THRESHOLD):
                content = self._truncate_to_first_section(topic, lines)

            result = {
                'type': 'static_guide',
                'topic': topic,
                'file': filename,
                'content': content
            }
            # BACK-926: guide topics that share a name with an adapter scheme
            # (ast, python, ssl, ...) get the same relationship-derived 'next'
            # pointers adapter-scheme help does; meta guides (tricks, schema,
            # ...) aren't scheme names so this is a no-op for them.
            self._add_related_next(result, topic)
            # BACK-936: same idea for the adapter's own see_also pointers.
            self._add_related_see_also(result, topic)
            if topic == 'schema':
                # BACK-847: 'schema' (singular, this guide) and 'schemas'
                # (plural, adapter query schemas) are unrelated pages that
                # happen to be one letter apart — cross-signpost so an agent
                # that meant the other one is redirected, not misinformed.
                result['note'] = (
                    'Looking for machine-readable adapter query schemas '
                    'instead? That is help://schemas/all (plural) — this '
                    'page is markdown front-matter validation.'
                )
                result['next'] = ['reveal help://schemas/all']
            elif topic == 'help':
                # BACK-930: same class of collision as BACK-847's schema/schemas
                # pair. 'help' is both this meta-guide (how the help system
                # works) and the help:// adapter's own scheme, so someone who
                # wants the topic index lands here instead — cross-signpost
                # rather than change dispatch. Appends to the curated 'next'
                # from _add_related_next above instead of overwriting it.
                result['note'] = (
                    'Looking for the topic index instead of an explanation '
                    'of how the help system works? That is bare '
                    'reveal help:// (no topic).'
                )
                result.setdefault('next', []).insert(0, 'reveal help://')
            elif topic == 'tricks':
                # BACK-997: this guide (prose, organized by workflow) and
                # help://examples/<task> (structured JSON recipes) both curate
                # task->command mappings but neither pointed at the other —
                # an agent landing on one had no signal the other exists.
                result['note'] = (
                    'Looking for machine-readable, per-task query recipes '
                    'instead of prose workflows? That is help://examples '
                    '(help://examples/security, help://examples/quality, ...).'
                )
                result.setdefault('next', []).insert(0, 'reveal help://examples')
            return result
        except FileNotFoundError:
            return {
                'type': 'static_guide',
                'topic': topic,
                'error': 'File not found',
                'message': f'Could not find {filename}',
                'next': ['reveal help://'],
            }
        except Exception as e:
            return {
                'type': 'static_guide',
                'topic': topic,
                'error': 'Load failed',
                'message': str(e),
                'next': ['reveal help://'],
            }

    def _extract_markdown_section(self, lines: list[str], section: str, topic: str) -> Optional[str]:
        """Extract a heading and its body from markdown lines.

        Case-insensitive substring match on heading text. Returns the matched heading
        line through the line before the next heading of equal or lesser depth, or EOF.
        Returns None if no matching heading is found.
        """
        import re as _re
        heading_re = _re.compile(r'^(#{1,6})\s+(.*)')
        needle = section.lower()

        match_start: Optional[int] = None
        match_level: int = 0

        for i, line in enumerate(lines):
            m = heading_re.match(line)
            if m:
                level = len(m.group(1))
                text = m.group(2).strip()
                if match_start is None:
                    if needle in text.lower():
                        match_start = i
                        match_level = level
                else:
                    # End of section: same or higher level heading
                    if level <= match_level:
                        return '\n'.join(lines[match_start:i])

        if match_start is not None:
            return '\n'.join(lines[match_start:])
        return None

    def _truncate_to_first_section(self, topic: str, lines: list[str]) -> str:
        """Return header + first meaningful content + section breadcrumb for large guides.

        Shows enough content to be useful: at least 2 sections or 60 lines of body,
        whichever cuts later — avoids the case where the first section is a skimpy
        1-paragraph intro (e.g. quick-start's "Installation" section).
        """
        section_indices = [i for i, line in enumerate(lines) if line.startswith('## ')]
        section_names = [lines[i][3:].strip() for i in section_indices]

        if section_indices:
            # Walk sections until we have at least 60 lines of body content
            cut_at = section_indices[1] if len(section_indices) >= 2 else len(lines)
            for i, idx in enumerate(section_indices[2:], start=2):
                if cut_at >= 60:
                    break
                cut_at = idx
            preview = '\n'.join(lines[:cut_at]).rstrip()
        else:
            preview = '\n'.join(lines[:80]).rstrip()

        breadcrumb = ' | '.join(section_names) if section_names else '(no sections)'
        shown_tokens = len(preview) // 4
        # Guides sometimes hand-author their own full-guide token estimate near
        # the top (e.g. AGENT_HELP.md's "**Token Cost:** ~40,000 tokens" banner).
        # Read top-to-bottom, that reads as the cost of *this* truncated output,
        # not the full guide it describes — BACK-1027: rewrite it in place so
        # the accurate number is the first thing seen, not a footer read only
        # after the misleading one was already paid for.
        preview = re.sub(
            r'\*\*Token Cost:\*\* ~[\d,]+ tokens',
            f'**Token Cost:** ~{shown_tokens:,} tokens shown here '
            f'(full guide: reveal help://{topic}/full)',
            preview,
            count=1,
        )
        footer = (
            f"\n\n── {len(lines)} lines total (~{shown_tokens:,} tokens shown here). "
            f"Sections: {breadcrumb}\n"
            f"── Full guide: reveal help://{topic}/full"
        )
        return preview + footer

    def _adapters_with_schema(self) -> List[str]:
        """Public adapter schemes that actually return a machine-readable schema.

        The bare `help://schemas` menu and the "did you mean" list are built from
        this rather than the raw registry, so an agent following the menu can
        never land on a meta-adapter (e.g. help://) that has no schema (N1).
        """
        schemes: List[str] = []
        for scheme, cls in _ADAPTER_REGISTRY.items():
            if scheme in self._INTERNAL_ADAPTERS:
                continue
            try:
                if cls.get_schema():
                    schemes.append(scheme)
            except Exception:
                # A schema that errors on generation isn't a usable menu entry.
                continue
        return sorted(schemes)

    def _get_rules_catalog(self) -> Dict[str, Any]:
        """help://rules — the pattern-detection rule catalog (BACK-846).

        Renders from RuleRegistry.list_rules(), the same source --rules uses,
        grouped by category. Internal self-check rules are excluded to match
        the flag's default (they can never fire on a user's codebase).
        """
        from ..rules import RuleRegistry

        rules = RuleRegistry.list_rules(include_internal=False)
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for rule in rules:
            by_category.setdefault(rule['category'], []).append(rule)

        return {
            'type': 'help_rules',
            'title': 'Reveal — Pattern Detection Rules',
            'rule_count': len(rules),
            'enabled_count': sum(1 for r in rules if r.get('enabled')),
            'categories': {
                cat: sorted(entries, key=lambda r: r['code'])
                for cat, entries in sorted(by_category.items())
            },
            'next': [
                'reveal help://schemas/index',
                'reveal help://quick',
            ],
        }

    def _get_languages_catalog(self) -> Dict[str, Any]:
        """help://languages — supported-language catalog (BACK-846).

        Renders from build_languages_payload(), the same structured source
        --languages formats its text from, so the two cannot drift.
        """
        from ..cli.languages import build_languages_payload

        payload = build_languages_payload()
        return {
            'type': 'help_languages',
            'title': 'Reveal — Supported Languages',
            'explicit': payload['explicit'],
            'fallback': payload['fallback'],
            'language_count': payload['total'],
            'ambiguous_extensions': payload['ambiguous'],
            'next': [
                'reveal help://quick',
                'reveal help://rules',
            ],
        }

    def _get_schema_all(self, thin: bool = False) -> Dict[str, Any]:
        """help://schemas/all (and .../index) — the aggregate schema view.

        Reuses build_discover_payload() (the same builder --discover uses) so
        the two surfaces can never drift apart. `thin=True` reduces each
        adapter entry to scheme/uri_syntax/description only — the ~1K index
        rung between the bare `help://schemas` menu and this full payload.
        """
        from ..cli.handlers.introspection import build_discover_payload

        payload = build_discover_payload(show_all=False)
        adapters = payload.get('adapters', {})
        if thin:
            adapters = {
                scheme: {
                    'scheme': entry.get('scheme', scheme),
                    'uri_syntax': entry.get('uri_syntax', ''),
                    'description': entry.get('description', ''),
                }
                for scheme, entry in adapters.items()
            }
        return {
            'type': 'adapter_schema_all',
            'thin': thin,
            'reveal_version': payload.get('reveal_version'),
            'adapter_count': payload.get('adapter_count', len(adapters)),
            'adapters': adapters,
            # BACK-847: cross-signpost — help://schema (singular) is the
            # unrelated front-matter validation guide, not an alias of this.
            'note': (
                'Looking for markdown front-matter validation instead? '
                'That is help://schema (singular) — this page is adapter '
                'query schemas (plural).'
            ),
            'next': (
                ['reveal help://schemas/all'] if thin
                else [f'reveal help://schemas/{s}' for s in sorted(adapters)[:3]]
            ),
        }

    # Only adapters far above the typical example count are trimmed; at 15 this
    # bites claude:// (43) alone and leaves every other adapter's list intact.
    _MAX_DEFAULT_EXAMPLES = 15

    def _summarize_schema(
        self, adapter_name: str, schema_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Trim a schema payload to its discovery tier.

        Two reductions, both reversible via ``help://schemas/<adapter>/full``:

        * Per-output-type JSON-Schema bodies are dropped. They are the bulk of a
          large adapter's payload (47% of claude://'s, once ~10,000 tokens) and
          nothing consumes them programmatically — ``--discover`` already reduces
          output_types to bare names and the contract-compliance tests read only
          ``['type']``. Names and descriptions stay, so the discovery answer
          ("what shapes can this adapter return?") survives intact.
        * Runaway example lists are capped, preserving authored order.
        """
        pointers: List[str] = []

        output_types = schema_data.get('output_types')
        if isinstance(output_types, list):
            summarized = []
            omitted = 0
            for entry in output_types:
                if not isinstance(entry, dict):
                    summarized.append(entry)
                    continue
                if 'schema' in entry:
                    omitted += 1
                    entry = {k: v for k, v in entry.items() if k != 'schema'}
                summarized.append(entry)
            if omitted:
                schema_data['output_types'] = summarized
                schema_data['output_types_detail'] = (
                    f'{omitted} output type(s) have a full JSON-Schema available '
                    f'on demand: reveal help://schemas/{adapter_name}/<output_type>'
                )
                first = summarized[0].get('type') if summarized else None
                if first:
                    pointers.append(
                        f'reveal help://schemas/{adapter_name}/{first}'
                    )

        examples = schema_data.get('example_queries')
        if isinstance(examples, list) and len(examples) > self._MAX_DEFAULT_EXAMPLES:
            total = len(examples)
            schema_data['example_queries'] = examples[:self._MAX_DEFAULT_EXAMPLES]
            schema_data['example_queries_detail'] = (
                f'Showing {self._MAX_DEFAULT_EXAMPLES} of {total} examples — '
                f'reveal help://schemas/{adapter_name}/full for all of them.'
            )
            pointers.append(f'reveal help://schemas/{adapter_name}/full')

        if pointers:
            existing = schema_data.setdefault('next', [])
            for p in pointers + [f'reveal help://schemas/{adapter_name}/full']:
                if p not in existing:
                    existing.append(p)
        return schema_data

    def _get_output_type_schema(
        self, adapter_name: str, schema_data: Dict[str, Any], type_name: str
    ) -> Dict[str, Any]:
        """Return one output type's full JSON-Schema (the drill-down tier)."""
        output_types = schema_data.get('output_types') or []
        available = [
            e.get('type') for e in output_types
            if isinstance(e, dict) and e.get('type')
        ]
        for entry in output_types:
            if isinstance(entry, dict) and entry.get('type') == type_name:
                # contract_version is stamped by get_element()'s setdefault
                # (BACK-696) — setting it here to a possibly-None value would
                # suppress that stamp.
                return {
                    'type': 'adapter_schema',
                    'adapter': adapter_name,
                    'output_type': type_name,
                    'detail': entry,
                    'next': [f'reveal help://schemas/{adapter_name}'],
                }
        return {
            'type': 'adapter_schema',
            'adapter': adapter_name,
            'error': 'Unknown output type',
            'message': (
                f"No output type '{type_name}' on {adapter_name}://. "
                f"Available: {', '.join(available)}"
            ),
            'available_output_types': available,
            'next': [f'reveal help://schemas/{adapter_name}'],
        }

    def _get_adapter_schema(
        self, adapter_name: str, section: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get machine-readable schema for an adapter.

        Args:
            adapter_name: Adapter scheme name (e.g., 'ssl', 'ast')
            section: ``None`` for the summarized default, ``'full'`` for the
                complete payload, or an output-type name to drill into one type.

        Returns:
            Schema dict or error dict if adapter not found or has no schema
        """
        adapter_class: Optional[type[Any]] = _ADAPTER_REGISTRY.get(adapter_name)
        if not adapter_class:
            # BACK-1028: a CLI-only subcommand (e.g. 'check', 'review') has no
            # URI adapter and never will, so the generic "no adapter" dead end
            # below is actively wrong for it — redirect to --help instead,
            # mirroring main.py's _check_ghost_flags() redirect at the CLI
            # flag-typo layer, one layer up at the help:// query layer.
            from ..main import _SUBCOMMANDS
            if adapter_name in _SUBCOMMANDS:
                return {
                    'type': 'adapter_schema',
                    'adapter': adapter_name,
                    'error': 'CLI-only subcommand',
                    'message': (
                        f"'{adapter_name}' is a CLI subcommand, not a URI adapter — "
                        f"it has no help://schemas entry. Use 'reveal {adapter_name} --help' "
                        f"for its flags instead."
                    ),
                    'next': [f'reveal {adapter_name} --help'],
                }
            # Only advertise adapters that actually have a schema, so the
            # "did you mean" list can't point at another dead end (N1).
            available = self._adapters_with_schema()
            return {
                'type': 'adapter_schema',
                'adapter': adapter_name,
                'error': 'Unknown adapter',
                'message': f"No adapter named '{adapter_name}'. Available: {', '.join(available)}",
                'available_adapters': available,
                'next': ['reveal help://schemas'],
            }

        if not hasattr(adapter_class, 'get_schema'):
            return {
                'type': 'adapter_schema',
                'adapter': adapter_name,
                'error': 'No schema available',
                'message': (
                    f'{adapter_class.__name__} does not provide '
                    f'machine-readable schema'
                ),
                'next': [f'reveal help://{adapter_name}'],
            }

        try:
            schema_data = adapter_class.get_schema()
            if not schema_data:
                # Adapter has get_schema() but returns None (e.g., help:// meta-adapter)
                return {
                    'type': 'adapter_schema',
                    'adapter': adapter_name,
                    'error': 'No schema available',
                    'message': (
                        f'{adapter_class.__name__} does not provide a machine-readable schema. '
                        f'This is expected for meta-adapters like help://'
                    ),
                    'next': [f'reveal help://{adapter_name}'],
                }
            # BACK-932: get_schema() returns most adapters' shared module-level
            # _SCHEMA dict by reference, not a fresh copy. Every mutation below
            # (and inside _summarize_schema, which reassigns 'output_types',
            # 'example_queries', 'next', etc.) was landing on that shared
            # object -- so calling the summary once permanently stripped
            # help://schemas/<adapter>/full's JSON-Schema bodies for the rest
            # of the process (confirmed live: full requested after a summary
            # call came back `is` the summary object itself). A long-lived
            # process like reveal-mcp would silently serve corrupted "full"
            # schemas after the first summary request. Only top-level keys
            # are ever reassigned (never nested structures mutated in place),
            # so a shallow copy is sufficient.
            schema_data = dict(schema_data)
            schema_data['adapter'] = adapter_name  # Ensure adapter is included
            schema_data['type'] = 'adapter_schema'
            if section and section != 'full':
                return self._get_output_type_schema(
                    adapter_name, schema_data, section
                )
            if section == 'full':
                return schema_data  # type: ignore[no-any-return]
            return self._summarize_schema(adapter_name, schema_data)
        except Exception as e:
            return {
                'type': 'adapter_schema',
                'adapter': adapter_name,
                'error': 'Schema generation failed',
                'message': str(e),
                'next': [f'reveal help://{adapter_name}'],
            }

    def _get_example_recipes(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Get canonical query recipes for a specific task."""
        if task_name not in _EXAMPLE_RECIPES:
            if not task_name:
                # BACK-998: the bare listing is a navigational index, not a
                # failure — give it its own success-typed shape (no 'error'
                # key) instead of overloading the "unknown task" error dict.
                # A JSON caller building an intent->task router should be able
                # to trust 'error' absence == valid response, not have to know
                # that this particular error is actually a listing.
                return {
                    'type': 'query_recipes_index',
                    'available_tasks': sorted(_EXAMPLE_RECIPES.keys()),
                    'next': [
                        f'reveal help://examples/{task}'
                        for task in sorted(_EXAMPLE_RECIPES)[:3]
                    ] + ['reveal help://quick'],
                    # BACK-997: reciprocal of the tricks->examples pointer above.
                    'see_also': ['reveal help://tricks — the same idea as prose, organized by workflow'],
                }
            available = ', '.join(sorted(_EXAMPLE_RECIPES.keys()))
            # BACK-841: a mistyped task name routes back to the catalog listing
            # above rather than looping on itself.
            return {
                'type': 'query_recipes',
                'task': task_name,
                'error': 'Unknown task',
                'message': f"Unknown task '{task_name}'. Available: {available}",
                'available_tasks': list(_EXAMPLE_RECIPES.keys()),
                'next': ['reveal help://examples'],
            }
        return _EXAMPLE_RECIPES[task_name]
