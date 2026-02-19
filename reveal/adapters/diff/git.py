"""Git resolution methods for diff adapter."""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, cast


def resolve_git_ref(git_ref: str, path: str) -> Dict[str, Any]:
    """Resolve a git reference to a structure.

    Args:
        git_ref: Git reference (HEAD, main, HEAD~1, etc.)
        path: Path to file or directory in the git tree

    Returns:
        Structure dict from the git version

    Raises:
        ValueError: If git command fails or path not found
    """
    # Check if we're in a git repository
    try:
        subprocess.run(['git', 'rev-parse', '--git-dir'],
                      check=True, capture_output=True)
    except subprocess.CalledProcessError:
        raise ValueError("Not in a git repository")

    # Check if it's a directory or file in git
    try:
        # Try to list the path to see if it's a directory
        result = subprocess.run(
            ['git', 'ls-tree', '-r', git_ref, path],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            raise ValueError(f"Path not found in {git_ref}: {path}")

        # If we got multiple lines, it's a directory
        lines = result.stdout.strip().split('\n')
        is_directory = len(lines) > 1 or lines[0].split()[1] == 'tree'

    except subprocess.CalledProcessError as e:
        raise ValueError(f"Git error: {e.stderr}")

    if is_directory:
        return resolve_git_directory(git_ref, path)
    else:
        return resolve_git_file(git_ref, path)


def resolve_git_adapter(resource: str) -> Dict[str, Any]:
    """Resolve git:// adapter URI to structure.

    Supports git:// adapter format: git://path@REF or git://.@REF

    Args:
        resource: Resource part of git:// URI (e.g., "reveal/main.py@HEAD" or ".@main")

    Returns:
        Structure dict from the git version (analyzed code structure, not file metadata)

    Raises:
        ImportError: If GitAdapter is not available (pygit2 not installed)
        ValueError: If URI format is invalid or resolution fails
    """
    try:
        from ..git.adapter import GitAdapter
    except ImportError:
        raise ImportError(
            "GitAdapter not available. Install with: pip install reveal-cli[git]\n"
            "Note: diff:// also supports git CLI format: git://REF/path"
        )

    # Validate git URI format - should have path@REF or .@REF format
    # Detect common mistake: REF:path instead of path@REF
    if ':' in resource and '@' not in resource:
        # Likely wrong format: "HEAD~1:file.py" instead of "file.py@HEAD~1"
        parts = resource.split(':', 1)
        raise ValueError(
            f"Git URI format error. Got '{resource}' but expected 'path@ref' format.\n"
            f"Hint: Use 'git://{parts[1]}@{parts[0]}' instead of 'git://{resource}'\n"
            f"Example: 'git://app.py@HEAD~1' (not 'git://HEAD~1:app.py')"
        )

    # Simple check: if no @ and no / in resource, it's likely just a ref without path
    if '@' not in resource and '/' not in resource and resource:
        raise ValueError(
            f"Git URI must be in format 'path@REF' or '.@REF'. "
            f"Got: '{resource}'. Example: 'main.py@HEAD' or '.@main'"
        )

    try:
        # GitAdapter will parse the resource (handles path@REF format)
        adapter = GitAdapter(resource=resource)
        git_result = adapter.get_structure()

        # If it's a file, we need to analyze its content to get code structure
        # GitAdapter returns file content/metadata, not analyzed code structure
        if git_result.get('type') in ['file', 'file_at_ref']:
            # Get the file content
            content = git_result.get('content', '')
            # Use the path for analyzer selection
            file_path = git_result.get('path', resource.split('@')[0])

            # Analyze the content to get code structure
            from ...registry import get_analyzer
            analyzer_class = get_analyzer(file_path, allow_fallback=True)
            if not analyzer_class:
                raise ValueError(f"No analyzer found for file: {file_path}")

            # Create temporary file or use in-memory analysis
            # Most analyzers can work with content directly
            with tempfile.NamedTemporaryFile(mode='w', suffix=os.path.splitext(file_path)[1], delete=False) as f:
                f.write(content)
                temp_path = f.name

            try:
                analyzer = analyzer_class(temp_path)
                return cast(Dict[str, Any], analyzer.get_structure())
            finally:
                os.unlink(temp_path)

        # For repository/ref views, return as-is
        return git_result

    except Exception as e:
        raise ValueError(f"Failed to resolve git:// adapter URI: {e}")


def resolve_git_file(git_ref: str, path: str) -> Dict[str, Any]:
    """Get structure from a file in git.

    Args:
        git_ref: Git reference
        path: File path in git tree

    Returns:
        Structure dict
    """
    from ...registry import get_analyzer

    # Get file content from git
    try:
        result = subprocess.run(
            ['git', 'show', f'{git_ref}:{path}'],
            capture_output=True, text=True, check=True
        )
        content = result.stdout
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to get file from git: {e.stderr}")

    # Write to temp file for analysis
    with tempfile.NamedTemporaryFile(mode='w', suffix=Path(path).suffix, delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        analyzer_class = get_analyzer(temp_path, allow_fallback=True)
        if not analyzer_class:
            raise ValueError(f"No analyzer found for file: {path}")
        analyzer = analyzer_class(temp_path)
        return cast(Dict[str, Any], analyzer.get_structure())
    finally:
        os.unlink(temp_path)


def _fetch_and_analyze_git_file(git_ref: str, file_path: str) -> Dict[str, Any]:
    """Fetch a file from git and analyze its structure.

    Returns the structure dict (functions/classes/imports), or raises on failure.
    """
    from ...registry import get_analyzer

    content_result = subprocess.run(
        ['git', 'show', f'{git_ref}:{file_path}'],
        capture_output=True, text=True, check=True
    )
    with tempfile.NamedTemporaryFile(mode='w', suffix=Path(file_path).suffix, delete=False) as f:
        f.write(content_result.stdout)
        temp_path = f.name

    try:
        analyzer_class = get_analyzer(temp_path, allow_fallback=False)
        if not analyzer_class:
            return {}
        structure = analyzer_class(temp_path).get_structure()
        return structure.get('structure', structure)
    finally:
        os.unlink(temp_path)


def _ls_tree_files(git_ref: str, dir_path: str) -> list:
    """Run git ls-tree and return list of blob file paths."""
    try:
        result = subprocess.run(
            ['git', 'ls-tree', '-r', git_ref, dir_path],
            capture_output=True, text=True, check=True
        )
        if not result.stdout.strip():
            raise ValueError(f"Directory not found in {git_ref}: {dir_path}")
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Git error: {e.stderr}")

    file_paths = []
    for line in result.stdout.strip().split('\n'):
        parts = line.split(maxsplit=3)
        if len(parts) == 4 and parts[1] == 'blob':
            file_paths.append(parts[3])
    return file_paths


def _tag_items_with_file(struct: Dict[str, Any], rel_path: str, key: str) -> list:
    """Return items from struct[key] with 'file' set to rel_path."""
    items = []
    for item in struct.get(key, []):
        item['file'] = rel_path
        items.append(item)
    return items


def resolve_git_directory(git_ref: str, dir_path: str) -> Dict[str, Any]:
    """Get aggregated structure from a directory in git.

    Args:
        git_ref: Git reference
        dir_path: Directory path in git tree

    Returns:
        Aggregated structure dict
    """
    from ...registry import get_analyzer

    file_paths = _ls_tree_files(git_ref, dir_path)

    all_functions: list = []
    all_classes: list = []
    all_imports: list = []
    file_count = 0

    for file_path in file_paths:
        if not get_analyzer(file_path, allow_fallback=False):
            continue
        try:
            struct = _fetch_and_analyze_git_file(git_ref, file_path)
        except Exception:
            continue
        if not struct:
            continue

        rel_path = file_path
        if dir_path and dir_path != '.':
            rel_path = file_path[len(dir_path.rstrip('/')) + 1:]

        all_functions.extend(_tag_items_with_file(struct, rel_path, 'functions'))
        all_classes.extend(_tag_items_with_file(struct, rel_path, 'classes'))
        all_imports.extend(_tag_items_with_file(struct, rel_path, 'imports'))
        file_count += 1

    return {
        'type': 'git_directory',
        'ref': git_ref,
        'path': dir_path,
        'file_count': file_count,
        'functions': all_functions,
        'classes': all_classes,
        'imports': all_imports
    }
