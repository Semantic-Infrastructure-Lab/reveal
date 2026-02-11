"""Scaffold new rule files."""

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


def _get_rule_prefix_and_severity(code: str):
    """Extract prefix and default severity from rule code."""
    prefix = code[0].upper()  # First letter

    # Map prefix to severity (common patterns)
    severity_map = {
        'B': 'HIGH',      # Bugs
        'E': 'LOW',       # Errors/Style
        'F': 'MEDIUM',    # Frontmatter/Format
        'C': 'MEDIUM',    # Complexity
        'D': 'MEDIUM',    # Duplicates
        'I': 'LOW',       # Imports
        'M': 'MEDIUM',    # Maintainability
        'N': 'LOW',       # Naming/Infrastructure
        'S': 'HIGH',      # Security
        'V': 'MEDIUM',    # Versioning
    }

    severity = severity_map.get(prefix, 'MEDIUM')
    return prefix, severity


def scaffold_rule(
    code: str,
    name: str,
    category: str = 'custom',
    output_dir: Optional[Path] = None,
    force: bool = False
) -> dict:
    """Generate scaffolding for a new quality rule.

    Args:
        code: Rule code (e.g., 'C999', 'M999')
        name: Rule name (e.g., 'custom_complexity')
        category: Rule category (complexity, maintainability, etc.)
        output_dir: Directory to create files in
        force: Overwrite existing files

    Returns:
        Dict with created file paths and next steps
    """
    from ...templates.rule_template import RULE_TEMPLATE, TEST_TEMPLATE, DOC_TEMPLATE

    # Normalize inputs
    code = code.upper()
    category = category.lower().replace(' ', '_').replace('-', '_')

    # Get prefix and severity
    prefix, severity = _get_rule_prefix_and_severity(code)

    # Determine category value (use RulePrefix enum if available, else string)
    known_prefixes = ['B', 'C', 'D', 'E', 'F', 'I', 'M', 'N', 'S', 'V']
    if prefix in known_prefixes:
        category_value = f"RulePrefix.{prefix}"
    else:
        category_value = f'"{prefix}"'  # Custom prefix as string

    # Determine output directory
    if output_dir is None:
        root = _find_reveal_root()
        rules_dir = root / 'reveal' / 'rules' / category
        tests_dir = root / 'tests'
        docs_dir = root / 'reveal' / 'docs' / 'rules'
    else:
        rules_dir = output_dir / 'rules' / category
        tests_dir = output_dir / 'tests'
        docs_dir = output_dir / 'docs' / 'rules'

    # File paths
    rule_file = rules_dir / f'{code}.py'
    test_file = tests_dir / f'test_{code.lower()}_rule.py'
    doc_file = docs_dir / f'{code}.md'

    # Check for existing files
    existing_files = []
    for f in [rule_file, test_file, doc_file]:
        if f.exists() and not force:
            existing_files.append(str(f))

    if existing_files:
        return {
            'error': 'Files already exist (use --force to overwrite)',
            'existing_files': existing_files
        }

    # Generate content
    rule_content = RULE_TEMPLATE.format(
        code=code,
        name=name,
        description=f'Detects {name} patterns in code.',
        prefix=prefix,
        category_value=category_value,
        severity=severity,
        file_patterns="['*']"  # Universal by default
    )

    test_content = TEST_TEMPLATE.format(
        code=code,
        name=name,
        category=category,
        file_patterns="['*']"
    )

    doc_content = DOC_TEMPLATE.format(
        code=code,
        name=name,
        description=f'Detects {name} patterns in code.',
        category=category,
        severity=severity,
        file_patterns="['*'] (all files)"
    )

    # Create directories if needed
    rules_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py if it doesn't exist
    init_file = rules_dir / '__init__.py'
    if not init_file.exists():
        init_file.write_text('"""Quality rules."""\n')

    # Write files
    rule_file.write_text(rule_content)
    test_file.write_text(test_content)
    doc_file.write_text(doc_content)

    return {
        'rule_file': str(rule_file),
        'test_file': str(test_file),
        'doc_file': str(doc_file),
        'next_steps': [
            f'1. Implement detection logic in {rule_file}',
            f'2. Add test cases to {test_file}',
            f'3. Run tests: pytest {test_file}',
            f'4. Test manually: reveal <file> --check --select={prefix}',
            f'5. Document examples in {doc_file}'
        ]
    }
