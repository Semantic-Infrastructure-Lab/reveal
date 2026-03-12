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


_KNOWN_PREFIXES = ['B', 'C', 'D', 'E', 'F', 'I', 'M', 'N', 'S', 'V']


def _get_category_value(prefix: str) -> str:
    """Return RulePrefix enum ref or quoted string for a prefix."""
    if prefix in _KNOWN_PREFIXES:
        return f"RulePrefix.{prefix}"
    return f'"{prefix}"'


def _determine_dirs(output_dir: Optional[Path], category: str):
    """Return (rules_dir, tests_dir, docs_dir) for given output_dir."""
    if output_dir is None:
        root = _find_reveal_root()
        return (
            root / 'reveal' / 'rules' / category,
            root / 'tests',
            root / 'reveal' / 'docs' / 'rules',
        )
    return (
        output_dir / 'rules' / category,
        output_dir / 'tests',
        output_dir / 'docs' / 'rules',
    )


def _generate_scaffold_content(code, name, category, prefix, category_value, severity):
    """Render rule, test, and doc templates; return (rule_content, test_content, doc_content)."""
    from ...templates.rule_template import RULE_TEMPLATE, TEST_TEMPLATE, DOC_TEMPLATE
    rule_content = RULE_TEMPLATE.format(
        code=code, name=name,
        description=f'Detects {name} patterns in code.',
        prefix=prefix, category_value=category_value, severity=severity,
        file_patterns="['*']",
    )
    test_content = TEST_TEMPLATE.format(
        code=code, name=name, category=category, file_patterns="['*']",
    )
    doc_content = DOC_TEMPLATE.format(
        code=code, name=name,
        description=f'Detects {name} patterns in code.',
        category=category, severity=severity,
        file_patterns="['*'] (all files)",
    )
    return rule_content, test_content, doc_content


def _write_scaffold_files(rules_dir, tests_dir, docs_dir, rule_file, test_file, doc_file,
                          rule_content, test_content, doc_content):
    """Create directories, init file, and write the three scaffold files."""
    rules_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    init_file = rules_dir / '__init__.py'
    if not init_file.exists():
        init_file.write_text('"""Quality rules."""\n', encoding='utf-8')
    rule_file.write_text(rule_content, encoding='utf-8')
    test_file.write_text(test_content, encoding='utf-8')
    doc_file.write_text(doc_content, encoding='utf-8')


def scaffold_rule(
    code: str,
    name: str,
    category: str = 'custom',
    output_dir: Optional[Path] = None,
    force: bool = False
) -> dict:
    """Generate scaffolding for a new quality rule."""
    code = code.upper()
    category = category.lower().replace(' ', '_').replace('-', '_')
    prefix, severity = _get_rule_prefix_and_severity(code)
    category_value = _get_category_value(prefix)

    rules_dir, tests_dir, docs_dir = _determine_dirs(output_dir, category)
    rule_file = rules_dir / f'{code}.py'
    test_file = tests_dir / f'test_{code.lower()}_rule.py'
    doc_file = docs_dir / f'{code}.md'

    existing_files = [str(f) for f in [rule_file, test_file, doc_file] if f.exists() and not force]
    if existing_files:
        return {'error': 'Files already exist (use --force to overwrite)', 'existing_files': existing_files}

    rule_content, test_content, doc_content = _generate_scaffold_content(
        code, name, category, prefix, category_value, severity
    )
    _write_scaffold_files(rules_dir, tests_dir, docs_dir, rule_file, test_file, doc_file,
                          rule_content, test_content, doc_content)

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
