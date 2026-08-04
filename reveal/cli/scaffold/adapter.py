"""Scaffold new adapter files."""

import sys
from pathlib import Path
from typing import Optional
from ...templates.adapter_template import (
    ADAPTER_TEMPLATE,
    RENDERER_TEMPLATE,
    INIT_TEMPLATE,
    TEST_TEMPLATE,
)


def scaffold_adapter(
    name: str,
    uri_scheme: str,
    output_dir: Optional[Path] = None,
    force: bool = False
) -> dict:
    """Generate scaffolding for a new adapter.

    Emits the package layout (adapters/<name>/{__init__,adapter,renderer}.py)
    — the shape CONTRIBUTING.md documents and 17/25 existing adapters already
    use, not a single monolithic file (BACK-917).

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
        /path/to/reveal/adapters/github/adapter.py
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
    adapter_dir = output_dir / 'reveal' / 'adapters' / adapter_name
    paths = {
        'adapter_dir': adapter_dir,
        'init_file': adapter_dir / '__init__.py',
        'adapter_file': adapter_dir / 'adapter.py',
        'renderer_file': adapter_dir / 'renderer.py',
        'test_file': output_dir / 'tests' / f'test_{adapter_name}_adapter.py',
        'doc_file': output_dir / 'reveal' / 'docs' / f'{adapter_name.upper()}_ADAPTER_GUIDE.md',
    }

    # Check for existing files
    existing = [str(p) for key, p in paths.items() if key != 'adapter_dir' and p.exists()]
    if existing and not force:
        print(f"Error: Files already exist: {', '.join(existing)}", file=sys.stderr)
        print("Use --force to overwrite", file=sys.stderr)
        return {'error': 'Files exist', 'existing_files': existing}

    names = {
        'adapter_name': adapter_name, 'class_name': class_name,
        'scheme': scheme, 'uri_scheme': uri_scheme,
    }
    _write_scaffold_files(names, paths)

    adapter_file, renderer_file, test_file, doc_file = (
        paths['adapter_file'], paths['renderer_file'], paths['test_file'], paths['doc_file']
    )
    return {
        'init_file': str(paths['init_file']),
        'adapter_file': str(adapter_file),
        'renderer_file': str(renderer_file),
        'test_file': str(test_file),
        'doc_file': str(doc_file),
        'next_steps': [
            f"1. Implement TODOs in {adapter_file.name} and {renderer_file.name}",
            f"2. Register it: add `from .{adapter_name} import {class_name}Adapter` to "
            f"reveal/adapters/__init__.py — reveal {uri_scheme} raises "
            f"'Unsupported URI scheme' until this import runs",
            f"3. Run tests: pytest {test_file.name}",
            f"4. Test manually: reveal {uri_scheme}",
            f"5. Document usage in {doc_file.name}"
        ]
    }


def _write_scaffold_files(names: dict, paths: dict) -> None:
    """Render the four templates and write them to their target paths."""
    init_content = INIT_TEMPLATE.format(class_name=names['class_name'])
    adapter_content = ADAPTER_TEMPLATE.format(
        **{k: names[k] for k in ('adapter_name', 'class_name', 'scheme')},
        description=f"{names['class_name']} adapter for {names['uri_scheme']} URIs",
    )
    renderer_content = RENDERER_TEMPLATE.format(
        **{k: names[k] for k in ('adapter_name', 'class_name')}
    )
    test_content = TEST_TEMPLATE.format(
        **{k: names[k] for k in ('adapter_name', 'class_name', 'scheme')}
    )

    paths['adapter_dir'].mkdir(parents=True, exist_ok=True)
    paths['init_file'].write_text(init_content)
    paths['adapter_file'].write_text(adapter_content)
    paths['renderer_file'].write_text(renderer_content)

    paths['test_file'].parent.mkdir(parents=True, exist_ok=True)
    paths['test_file'].write_text(test_content)

    paths['doc_file'].parent.mkdir(parents=True, exist_ok=True)
    paths['doc_file'].write_text(
        f"# {names['class_name']} Adapter\n\nTODO: Document {names['uri_scheme']} adapter usage.\n"
    )


def _find_reveal_root() -> Optional[Path]:
    """Find reveal project root by looking for reveal/adapters/."""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / 'reveal' / 'adapters').is_dir():
            return parent
    return None
