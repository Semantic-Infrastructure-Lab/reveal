"""Scaffold new adapter files."""

import sys
from pathlib import Path
from typing import Optional
from ...templates.adapter_template import ADAPTER_TEMPLATE, RENDERER_TEMPLATE, TEST_TEMPLATE


def scaffold_adapter(
    name: str,
    uri_scheme: str,
    output_dir: Optional[Path] = None,
    force: bool = False
) -> dict:
    """Generate scaffolding for a new adapter.

    Args:
        name: Adapter name (e.g., 'github', 'docker')
        uri_scheme: URI scheme (e.g., 'github://', 'docker://')
        output_dir: Directory to create files in (default: current reveal project)
        force: Overwrite existing files

    Returns:
        Dict with created file paths and next steps

    Example:
        >>> result = scaffold_adapter('github', 'github://')
        >>> print(result['adapter_file'])
        /path/to/reveal/adapters/github.py
    """
    if output_dir is None:
        output_dir = _find_reveal_root()
        if output_dir is None:
            print("Error: Not in a reveal project. Specify output_dir explicitly.", file=sys.stderr)
            return {'error': 'Not in reveal project'}

    # Normalize names
    adapter_name = name.lower().replace('-', '_')
    class_name = ''.join(word.capitalize() for word in adapter_name.split('_'))
    scheme = uri_scheme.rstrip('://').lower()

    # File paths
    adapter_file = output_dir / 'reveal' / 'adapters' / f'{adapter_name}.py'
    test_file = output_dir / 'tests' / f'test_{adapter_name}_adapter.py'
    doc_file = output_dir / 'reveal' / 'docs' / f'{adapter_name.upper()}_ADAPTER_GUIDE.md'

    # Check for existing files
    existing = []
    if adapter_file.exists():
        existing.append(str(adapter_file))
    if test_file.exists():
        existing.append(str(test_file))
    if doc_file.exists():
        existing.append(str(doc_file))

    if existing and not force:
        print(f"Error: Files already exist: {', '.join(existing)}", file=sys.stderr)
        print("Use --force to overwrite", file=sys.stderr)
        return {'error': 'Files exist', 'existing_files': existing}

    # Generate files
    adapter_content = ADAPTER_TEMPLATE.format(
        adapter_name=adapter_name,
        class_name=class_name,
        scheme=scheme,
        description=f"{class_name} adapter for {uri_scheme} URIs"
    )

    test_content = TEST_TEMPLATE.format(
        adapter_name=adapter_name,
        class_name=class_name,
        scheme=scheme
    )

    # Write files
    adapter_file.parent.mkdir(parents=True, exist_ok=True)
    adapter_file.write_text(adapter_content)

    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(test_content)

    # Create placeholder doc
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text(f"# {class_name} Adapter\n\nTODO: Document {uri_scheme} adapter usage.\n")

    return {
        'adapter_file': str(adapter_file),
        'test_file': str(test_file),
        'doc_file': str(doc_file),
        'next_steps': [
            f"1. Implement TODOs in {adapter_file.name}",
            f"2. Run tests: pytest {test_file.name}",
            f"3. Test manually: reveal {uri_scheme}",
            f"4. Document usage in {doc_file.name}"
        ]
    }


def _find_reveal_root() -> Optional[Path]:
    """Find reveal project root by looking for reveal/adapters/."""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / 'reveal' / 'adapters').is_dir():
            return parent
    return None
