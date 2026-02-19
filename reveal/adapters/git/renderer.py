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
        elif result_type in ('file_history', 'git_file_history'):
            GitRenderer._render_file_history(result)
        elif result_type in ('file_blame', 'git_file_blame'):
            GitRenderer._render_file_blame(result)
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
        print(f"File History: {result['path']} @ {result['ref']}")
        print(f"Commits: {result['count']}")
        print()

        for commit in result['commits']:
            print(f"  {commit['hash']} {commit['date']} {commit['author']}")
            print(f"    {commit['message']}")

    @staticmethod
    def _render_file_blame(result: dict) -> None:
        """Render file blame with progressive disclosure."""
        # Check if detail mode is requested
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
    def _render_file_blame_summary(result: dict) -> None:
        """Render blame summary (default view)."""
        # Check if this is semantic blame (element-specific)
        element = result.get('element')
        if element:
            print(f"Element Blame: {result['path']} → {element['name']}")
            print(f"Lines {element['line_start']}-{element['line_end']} ({len(result['hunks'])} hunks)")
        else:
            print(f"File Blame Summary: {result['path']} ({result['lines']} lines, {len(result['hunks'])} hunks)")
        print()

        # Calculate contributor stats
        contributors = {}
        for hunk in result['hunks']:
            author = hunk['commit']['author']
            lines = hunk['lines']['count']
            if author not in contributors:
                contributors[author] = {'lines': 0, 'hunks': 0, 'latest_date': hunk['commit']['date']}
            contributors[author]['lines'] += lines
            contributors[author]['hunks'] += 1
            # Track latest commit date
            if hunk['commit']['date'] > contributors[author]['latest_date']:
                contributors[author]['latest_date'] = hunk['commit']['date']

        # Sort by lines contributed (descending)
        sorted_contributors = sorted(contributors.items(), key=lambda x: x[1]['lines'], reverse=True)

        print("Contributors (by lines owned):")
        total_lines = result['lines']
        for author, stats in sorted_contributors[:5]:  # Top 5 contributors
            pct = (stats['lines'] / total_lines * 100) if total_lines > 0 else 0
            print(f"  {author:30} {stats['lines']:4} lines ({pct:5.1f}%)  Last: {stats['latest_date']}")

        if len(sorted_contributors) > 5:
            print(f"  ... and {len(sorted_contributors) - 5} more contributors")
        print()

        # Find key hunks (largest continuous blocks)
        key_hunks = sorted(result['hunks'], key=lambda h: h['lines']['count'], reverse=True)[:5]

        print("Key hunks (largest continuous blocks):")
        for hunk in key_hunks:
            lines_info = hunk['lines']
            commit_info = hunk['commit']
            start = lines_info['start']
            end = start + lines_info['count'] - 1
            print(f"  Lines {start:3}-{end:3} ({lines_info['count']:3} lines)  {commit_info['hash']} {commit_info['date']} {commit_info['author'][:20]}")
            print(f"    {commit_info['message'][:70]}")
        print()

        print(f"Use: reveal git://{result['path']}?type=blame&detail=full for line-by-line view")

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
