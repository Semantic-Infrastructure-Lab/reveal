"""Git repository rendering for text and JSON output."""

import json
import sys


class GitRenderer:
    """Renderer for git repository inspection results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render git repository structure.

        Args:
            result: Git structure from adapter
            format: Output format (text, json)
        """
        if format == 'json':
            print(json.dumps(result, indent=2))
            return

        # Text rendering based on result type
        result_type = result.get('type', 'unknown')

        if result_type in ('repository', 'git_repository'):
            GitRenderer._render_repository_overview(result)
        elif result_type in ('ref', 'git_ref'):
            GitRenderer._render_ref_structure(result)
        elif result_type in ('file', 'git_file'):
            GitRenderer._render_file(result)
        elif result_type == 'git_file_structure':
            GitRenderer._render_file_structure(result)
        elif result_type == 'git_file_diff':
            GitRenderer._render_file_diff(result)
        elif result_type in ('file_history', 'git_file_history'):
            GitRenderer._render_file_history(result)
        elif result_type in ('file_blame', 'git_file_blame'):
            GitRenderer._render_file_blame(result)
        elif result_type == 'git_ownership':
            GitRenderer._render_ownership(result)
        else:
            print(json.dumps(result, indent=2))

    @staticmethod
    def _render_repository_overview(result: dict) -> None:
        """Render repository overview."""
        print(f"Repository: {result['path']}")
        print()

        head = result['head']
        if head['branch']:
            print(f"HEAD: {head['branch']} @ {head['commit']}")
        elif head['detached']:
            print(f"HEAD: (detached) @ {head['commit']}")
        print()

        print(f"Branches: {result['branches']['count']}")
        for branch in result['branches']['recent']:
            print(f"  • {branch['name']:<20} {branch['commit']} {branch['date']} {branch['message']}")
        print()

        print(f"Tags: {result['tags']['count']}")
        for tag in result['tags']['recent']:
            print(f"  • {tag['name']:<20} {tag['commit']} {tag['date']} {tag['message']}")
        print()

        print("Recent Commits:")
        for commit in result['commits']['recent']:
            print(f"  {commit['hash']} {commit['date']} {commit['author']}")
            print(f"    {commit['message']}")

    @staticmethod
    def _render_ref_structure(result: dict) -> None:
        """Render ref/commit history."""
        print(f"Ref: {result['ref']}")
        print()

        commit = result['commit']
        print(f"Commit: {commit['full_hash']}")
        print(f"Author: {commit['author']} <{commit['email']}>")
        print(f"Date:   {commit['date']}")
        print()
        print(commit['full_message'])
        print()

        print("History:")
        if not result['history']:
            if result.get('filter_applied'):
                print("  (no commits matched filter — use '~=' for substring match, e.g., author~=name)")
            else:
                print("  (no commits)")
        for c in result['history']:
            print(f"  {c['hash']} {c['date']} {c['author']}")
            print(f"    {c['message']}")

    @staticmethod
    def _render_file(result: dict) -> None:
        """Render file contents."""
        print(f"File: {result['path']} @ {result['ref']}")
        print(f"Commit: {result['commit']}")
        print(f"Size: {result['size']} bytes, {result['lines']} lines")
        print()
        print(result['content'])

    @staticmethod
    def _render_file_history(result: dict) -> None:
        """Render file history."""
        element = result.get('element')
        if element:
            print(f"Element History: {result['path']} → {element} @ {result['ref']}")
        else:
            print(f"File History: {result['path']} @ {result['ref']}")
        print(f"Commits: {result['count']}")
        print()

        for commit in result['commits']:
            print(f"  {commit['hash']} {commit['date']} {commit['author']}")
            print(f"    {commit['message']}")

    @staticmethod
    def _render_file_blame(result: dict) -> None:
        """Render file blame with progressive disclosure."""
        if result.get('shallow_clone'):
            print("⚠ Shallow clone detected — blame attribution is limited to the fetched history.")
            print("  Run `git fetch --unshallow` for complete bus-factor / key-person data.")
            print()

        detail_mode = result.get('detail', False)

        if detail_mode:
            # Detailed view: show all hunks (original behavior)
            print(f"File Blame (Detailed): {result['path']} @ {result['ref']}")
            print(f"Lines: {result['lines']}")
            print()

            for hunk in result['hunks']:
                lines_info = hunk['lines']
                commit_info = hunk['commit']
                print(f"Lines {lines_info['start']}-{lines_info['start'] + lines_info['count'] - 1}:")
                print(f"  {commit_info['hash']} {commit_info['date']} {commit_info['author']}")
                print(f"  {commit_info['message']}")
                print()
        else:
            # Summary view: show contributors and key hunks
            GitRenderer._render_file_blame_summary(result)

    @staticmethod
    def _build_contributors(hunks: list) -> dict:
        contributors: dict = {}
        for hunk in hunks:
            author = hunk['commit']['author']
            lines = hunk.get('clipped_lines', hunk['lines']['count'])
            if author not in contributors:
                contributors[author] = {'lines': 0, 'hunks': 0, 'latest_date': hunk['commit']['date']}
            contributors[author]['lines'] += lines
            contributors[author]['hunks'] += 1
            if hunk['commit']['date'] > contributors[author]['latest_date']:
                contributors[author]['latest_date'] = hunk['commit']['date']
        return contributors

    @staticmethod
    def _render_contributors(sorted_contributors: list, total_lines: int) -> None:
        print("Contributors (by lines owned):")
        for author, stats in sorted_contributors[:5]:
            pct = (stats['lines'] / total_lines * 100) if total_lines > 0 else 0
            print(f"  {author:30} {stats['lines']:4} lines ({pct:5.1f}%)  Last: {stats['latest_date']}")
        if len(sorted_contributors) > 5:
            print(f"  ... and {len(sorted_contributors) - 5} more contributors")
        print()

    @staticmethod
    def _render_ignored_commits(ignored: list) -> None:
        auto_ignored = [e for e in ignored if e.get('source') in ('auto-detect', 'ignore-revs')]
        explicit_ignored = [e for e in ignored if e.get('source') not in ('auto-detect', 'ignore-revs')]
        if auto_ignored:
            print(f"Auto-ignored {len(auto_ignored)} noise commit(s) — use ?ignore=off to include:")
            for entry in auto_ignored:
                src = '.git-blame-ignore-revs' if entry.get('source') == 'ignore-revs' else 'noise heuristic'
                print(f"  {entry['hash']}  {entry['lines']:4} lines  {entry['message'][:55]}  [{src}]")
            print()
        if explicit_ignored:
            total_lines = sum(e['lines'] for e in explicit_ignored)
            print(f"Suppressed ({len(explicit_ignored)} user-specified commit(s), {total_lines} lines excluded):")
            for entry in explicit_ignored:
                print(f"  {entry['hash']}  {entry['lines']:4} lines  {entry['message'][:60]}")
            print()

    @staticmethod
    def _render_key_hunks(hunks: list) -> None:
        key_hunks = sorted(hunks, key=lambda h: h['lines']['count'], reverse=True)[:5]
        print("Key hunks (largest continuous blocks):")
        for hunk in key_hunks:
            lines_info = hunk['lines']
            commit_info = hunk['commit']
            start = lines_info['start']
            end = start + lines_info['count'] - 1
            print(f"  Lines {start:3}-{end:3} ({lines_info['count']:3} lines)  {commit_info['hash']} {commit_info['date']} {commit_info['author'][:20]}")
            print(f"    {commit_info['message'][:70]}")
        print()

    @staticmethod
    def _render_file_blame_summary(result: dict) -> None:
        """Render blame summary (default view)."""
        element = result.get('element')
        if element:
            print(f"Element Blame: {result['path']} → {element['name']}")
            print(f"Lines {element['line_start']}-{element['line_end']} ({len(result['hunks'])} hunks)")
        else:
            print(f"File Blame Summary: {result['path']} ({result['lines']} lines, {len(result['hunks'])} hunks)")
        print()

        contributors = GitRenderer._build_contributors(result['hunks'])
        sorted_contributors = sorted(contributors.items(), key=lambda x: x[1]['lines'], reverse=True)
        total_lines = (element['line_end'] - element['line_start'] + 1) if element else result['lines']
        GitRenderer._render_contributors(sorted_contributors, total_lines)

        ignored = result.get('ignored')
        if ignored:
            GitRenderer._render_ignored_commits(ignored)

        GitRenderer._render_key_hunks(result['hunks'])
        print(f"Use: reveal git://{result['path']}?type=blame&detail=full for line-by-line view")

    @staticmethod
    def _render_ownership(result: dict) -> None:
        """Render commit-share ownership for a file, directory, or repository."""
        if result.get('shallow_clone'):
            print("⚠ Shallow clone detected — ownership shares are limited to the fetched history.")
            print("  Run `git fetch --unshallow` for complete bus-factor / key-person data.")
            print()

        label = result['source_type'].capitalize()
        print(f"Ownership ({label}): {result['path']} @ {result['ref']}")
        print(f"Commits: {result['total_commits']}  ·  Contributors: {result['contributor_count']}  ·  Last touch: {result['last_touch'] or '—'}")
        print()

        authors = result['authors']
        if not authors:
            print("  (no commits touch this path in the walked history)")
            print()
            return

        print("Authors (by commit-share):")
        for a in authors[:10]:
            pct = a['share'] * 100
            print(f"  {a['name'][:28]:28} {a['commits']:5} commits ({pct:5.1f}%)  Last: {a['last_touch']}")
        if len(authors) > 10:
            print(f"  ... and {len(authors) - 10} more contributors")
        print()
        print("ℹ Commit-share (not surviving-line ownership) — use ?type=blame for line-level attribution.")

    @staticmethod
    def _render_file_structure(result: dict) -> None:
        """Render structural view of a file at a historical ref."""
        ci = result.get('commit_info', {})
        print(f"File: {result['path']} @ {result['ref']}")
        print(f"Commit: {result['commit']}  {ci.get('date', '')}  {ci.get('author', '')} — \"{ci.get('message', '')}\"")
        print(f"Size: {result['size']:,} bytes, {result['lines']:,} lines")
        print()

        structure = result.get('structure', {})
        if not structure:
            print("(no structured analysis available for this file type — use ?raw=1 for contents)")
            return

        functions = structure.get('functions', [])
        classes = structure.get('classes', [])
        imports = structure.get('imports', [])

        if classes:
            print(f"Classes ({len(classes)}):")
            for cls in classes:
                line_count = cls.get('line_end', cls['line']) - cls['line'] + 1
                print(f"  :{cls['line']:<6} {cls['name']} [{line_count} lines]")
            print()

        if functions:
            print(f"Functions ({len(functions)}):")
            for fn in functions:
                line_count = fn.get('line_end', fn['line']) - fn['line'] + 1
                print(f"  :{fn['line']:<6} {fn['name']} [{line_count} lines]")
            print()

        if imports:
            print(f"Imports ({len(imports)}):")
            for imp in imports[:10]:
                name = imp if isinstance(imp, str) else imp.get('name', str(imp))
                print(f"  {name}")
            if len(imports) > 10:
                print(f"  ... and {len(imports) - 10} more")
            print()

        print(f"Use: reveal 'git://{result['path']}@{result['ref']}?raw=1' for full file contents")

    @staticmethod
    def _render_file_diff(result: dict) -> None:
        """Render a commit diff for a single file."""
        ci = result['commit_info']
        print(f"Diff: {result['path']} @ {result['commit']} (vs parent)")
        print(f"Commit: {ci['hash']}  {ci['date']}  {ci['author']} — \"{ci['message']}\"")
        if result.get('element_filter'):
            print(f"Element filter: {result['element_filter']}")
        print()
        print(result['diff_text'])

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render error message."""
        print(f"Error: {error}", file=sys.stderr)
        if isinstance(error, ImportError):
            # pygit2 not installed
            print(file=sys.stderr)
            print("The git:// adapter requires pygit2.", file=sys.stderr)
            print("Install with: pip install reveal-cli[git]", file=sys.stderr)
            print("Alternative: pip install pygit2>=1.14.0", file=sys.stderr)
            print(file=sys.stderr)
            print("For more info: reveal help://git", file=sys.stderr)
