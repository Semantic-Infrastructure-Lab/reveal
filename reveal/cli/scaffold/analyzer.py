"""Scaffold new analyzer files."""

from pathlib import Path
from typing import Optional


def _find_reveal_root() -> Path:
    """Find reveal project root directory."""
    current = Path(__file__).parent
    while current != current.parent:
        if (current / 'reveal' / '__init__.py').exists():
            return current
        current = current.parent
    # Fallback: assume we're in reveal/ already
    return Path(__file__).parent.parent.parent


def _to_class_name(name: str) -> str:
    """Convert name to PascalCase class name."""
    return ''.join(word.capitalize() for word in name.replace('-', '_').replace(' ', '_').split('_'))


def _to_module_name(name: str) -> str:
    """Convert name to snake_case module name."""
    return name.lower().replace('-', '_').replace(' ', '_')


def scaffold_analyzer(
    name: str,
    extension: str,
    output_dir: Optional[Path] = None,
    force: bool = False
) -> dict:
    """Generate scaffolding for a new analyzer.

    Args:
        name: Analyzer name (e.g., 'xyz', 'custom_lang')
        extension: File extension (e.g., '.xyz', '.custom')
        output_dir: Directory to create files in
        force: Overwrite existing files

    Returns:
        Dict with created file paths and next steps
    """
    from ...templates.analyzer_template import ANALYZER_TEMPLATE, TEST_TEMPLATE, DOC_TEMPLATE

    # Normalize inputs
    if not extension.startswith('.'):
        extension = f'.{extension}'

    class_name = _to_class_name(name)
    module_name = _to_module_name(name)
    display_name = name.replace('_', ' ').replace('-', ' ').title()
    language = module_name  # Assume tree-sitter language matches module name
    icon = ''  # Default emoji (can be customized)

    # Determine output directory
    if output_dir is None:
        root = _find_reveal_root()
        analyzers_dir = root / 'reveal' / 'analyzers'
        tests_dir = root / 'tests'
        docs_dir = root / 'reveal' / 'docs'
    else:
        analyzers_dir = output_dir / 'analyzers'
        tests_dir = output_dir / 'tests'
        docs_dir = output_dir / 'docs'

    # File paths
    analyzer_file = analyzers_dir / f'{module_name}.py'
    test_file = tests_dir / f'test_{module_name}_analyzer.py'
    doc_file = docs_dir / f'{module_name.upper()}_ANALYZER_GUIDE.md'

    # Check for existing files
    existing_files = []
    for f in [analyzer_file, test_file, doc_file]:
        if f.exists() and not force:
            existing_files.append(str(f))

    if existing_files:
        return {
            'error': 'Files already exist (use --force to overwrite)',
            'existing_files': existing_files
        }

    # Generate content
    analyzer_content = ANALYZER_TEMPLATE.format(
        description=f'{display_name} file analyzer',
        extension=extension,
        display_name=display_name,
        icon=icon,
        class_name=class_name,
        language=language
    )

    test_content = TEST_TEMPLATE.format(
        class_name=class_name,
        module_name=module_name,
        language=language,
        extension=extension,
        display_name=display_name
    )

    doc_content = DOC_TEMPLATE.format(
        display_name=display_name,
        extension=extension,
        language=language,
        module_name=module_name,
        class_name=class_name
    )

    # Create directories if needed
    analyzers_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Write files
    analyzer_file.write_text(analyzer_content)
    test_file.write_text(test_content)
    doc_file.write_text(doc_content)

    return {
        'analyzer_file': str(analyzer_file),
        'test_file': str(test_file),
        'doc_file': str(doc_file),
        'next_steps': [
            f'1. Install tree-sitter-{language}: pip install tree-sitter-{language}',
            f'2. Add sample {display_name} code to {test_file}',
            f'3. Run tests: pytest {test_file}',
            f'4. Test manually: reveal <file{extension}>',
            f'5. Document usage in {doc_file}'
        ]
    }
