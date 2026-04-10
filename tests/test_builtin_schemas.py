"""Tests for built-in schemas (Hugo, Jekyll, MkDocs, Obsidian).

Tests schema validation with real-world examples and edge cases.
"""

import pytest
import tempfile
import subprocess
import os
from pathlib import Path
from conftest import _run_reveal_direct


def run_reveal(args, check=True):
    """Run reveal in-process (no subprocess overhead).

    Args:
        args: List of command-line arguments
        check: If True, raise CalledProcessError on non-zero exit

    Returns:
        Object with .stdout, .stderr, .returncode attributes
    """
    result = _run_reveal_direct(*args)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, ['reveal'] + args, result.stdout, result.stderr
        )
    return result


def _validate_schema_api(content: str, schema_name: str) -> list:
    """Validate markdown content against a schema using the Python API.

    Avoids subprocess overhead for tests that only need to check whether
    a given piece of front matter passes or fails schema validation.

    Returns:
        List of Detection objects — empty means valid.
    """
    from reveal.registry import get_analyzer
    from reveal.schemas.frontmatter import load_schema
    from reveal.rules.frontmatter import set_validation_context, clear_validation_context
    from reveal.rules import RuleRegistry

    schema = load_schema(schema_name)
    assert schema is not None, f"Schema '{schema_name}' not found"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(content)
        path = f.name

    try:
        analyzer_class = get_analyzer(path)
        analyzer = analyzer_class(path)
        structure = analyzer.get_structure(extract_frontmatter=True)
        file_content = analyzer.content

        set_validation_context(schema)
        try:
            return RuleRegistry.check_file(path, structure, file_content, select=['F'], ignore=None)
        finally:
            clear_validation_context()
    finally:
        os.unlink(path)


@pytest.mark.slow
class TestHugoSchema:
    """Test Hugo static site schema validation."""

    def test_hugo_schema_loads(self):
        """Test hugo schema loads successfully."""
        from reveal.schemas.frontmatter import load_schema
        schema = load_schema('hugo')
        assert schema is not None
        assert schema['name'] == 'Hugo Static Site Schema'
        assert 'title' in schema['required_fields']
        assert 'date' in schema['optional_fields']  # Date is optional (for static pages)

    def test_hugo_valid_post(self):
        """Test validation passes for valid Hugo post."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "My Blog Post"
date: 2026-01-02
draft: false
tags: ["python", "testing"]
categories: ["development"]
description: "A great blog post about testing"
---

# My Blog Post

Content here.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo'])
            assert result.returncode == 0
            # Should have no detections for valid post
            assert 'Found 0 issues' in result.stdout or 'No issues found' in result.stdout or result.stdout.strip() == ''
        finally:
            Path(temp_path).unlink()

    def test_hugo_missing_required_title(self):
        """Test validation fails when title is missing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
date: 2026-01-02
---

# Post without frontmatter title
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo'], check=False)
            assert result.returncode != 0
            assert 'F003' in result.stdout  # Required field missing
            assert 'title' in result.stdout.lower()
        finally:
            Path(temp_path).unlink()

    def test_hugo_date_optional_for_static_pages(self):
        """Test validation passes when date is missing (static pages don't need dates)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "About Page"
description: "Static page without date"
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo'])
            assert result.returncode == 0  # Should pass - date is optional
            assert 'No issues found' in result.stdout or 'Found 0 issues' in result.stdout or result.stdout.strip() == ''
        finally:
            Path(temp_path).unlink()

    def test_hugo_empty_title(self):
        """Test validation fails when title is empty string."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: ""
date: 2026-01-02
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo'], check=False)
            assert result.returncode != 0
            assert 'F005' in result.stdout  # Custom validation rule
            assert 'Title cannot be empty' in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_hugo_invalid_date_format(self):
        """Test validation fails for invalid date format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "My Post"
date: 01/02/2026
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo'], check=False)
            assert result.returncode != 0
            assert 'F005' in result.stdout  # Custom validation rule
            assert 'YYYY-MM-DD' in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_hugo_wrong_field_types(self):
        """Test validation fails for wrong field types."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "My Post"
date: 2026-01-02
draft: "yes"
tags: "python"
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo'], check=False)
            assert result.returncode != 0
            assert 'F004' in result.stdout  # Wrong type
            # Should detect draft should be boolean and tags should be list
        finally:
            Path(temp_path).unlink()

    def test_hugo_with_all_optional_fields(self):
        """Test validation passes with all optional fields."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "Complete Post"
date: 2026-01-02
draft: false
tags: ["python", "testing", "hugo"]
categories: ["development", "tutorial"]
description: "A comprehensive guide to testing"
author: "Scott"
slug: "complete-hugo-post"
weight: 10
featured_image: "/images/hero.jpg"
summary: "Learn how to write comprehensive Hugo posts"
toc: true
type: "post"
layout: "single"
---

# Complete Post

Full content with all metadata.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()

    def test_hugo_json_output(self):
        """Test Hugo validation with JSON output format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "Test Post"
description: "Static page without date"
---

# Test Post (date optional for static pages)
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo', '--format', 'json'])
            assert result.returncode == 0  # Should pass - date is optional
            # Should be valid JSON
            import json
            data = json.loads(result.stdout)
            assert 'detections' in data or isinstance(data, list)
            assert data['total'] == 0  # No detections
        finally:
            Path(temp_path).unlink()


@pytest.mark.slow
class TestObsidianSchema:
    """Test Obsidian vault schema validation."""

    def test_obsidian_schema_loads(self):
        """Test obsidian schema loads successfully."""
        from reveal.schemas.frontmatter import load_schema
        schema = load_schema('obsidian')
        assert schema is not None
        assert schema['name'] == 'Obsidian Vault Schema'
        # Obsidian has no required fields
        assert schema.get('required_fields', []) == []

    def test_obsidian_no_frontmatter(self):
        """Test Obsidian allows notes without frontmatter."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''# My Note

Just a simple note without any frontmatter.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'], check=False)
            # Should warn about missing frontmatter (F001) but that's okay for Obsidian
            # Since no required fields, it's not an error
            assert 'F001' in result.stdout  # Missing frontmatter warning
        finally:
            Path(temp_path).unlink()

    def test_obsidian_valid_note(self):
        """Test validation passes for valid Obsidian note."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
tags: [personal, productivity, notes]
aliases: [productivity-tips, getting-things-done]
cssclass: clean
publish: true
created: 2026-01-02
---

# Productivity Tips

My notes on staying productive.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()

    def test_obsidian_empty_tags_list(self):
        """Test validation warns about empty tags list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
tags: []
---

# Note with empty tags
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'], check=False)
            assert result.returncode != 0
            assert 'F005' in result.stdout  # Custom validation
            assert 'at least one tag' in result.stdout.lower()
        finally:
            Path(temp_path).unlink()

    def test_obsidian_wrong_field_types(self):
        """Test validation fails for wrong field types."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
tags: "single-tag"
aliases: "not-a-list"
publish: "yes"
---

# Note with wrong types
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'], check=False)
            assert result.returncode != 0
            assert 'F004' in result.stdout  # Wrong type
        finally:
            Path(temp_path).unlink()

    def test_obsidian_rating_validation(self):
        """Test rating field must be 1-5."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
rating: 10
---

# Note with invalid rating
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'], check=False)
            assert result.returncode != 0
            assert 'F005' in result.stdout
            assert 'between 1 and 5' in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_obsidian_priority_validation(self):
        """Test priority field must be 1-5."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
priority: 0
---

# Note with invalid priority
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'], check=False)
            assert result.returncode != 0
            assert 'F005' in result.stdout
            assert 'between 1 and 5' in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_obsidian_valid_rating(self):
        """Test valid rating values (1-5) pass validation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
rating: 4
priority: 2
tags: [important]
---

# Well-rated note
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()

    def test_obsidian_cssclasses_vs_cssclass(self):
        """Test both cssclass (string) and cssclasses (list) work."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
cssclass: minimal
cssclasses: [wide, clean]
tags: [meta]
---

# Note with CSS styling
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()

    def test_obsidian_all_fields(self):
        """Test validation with all Obsidian fields."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
tags: [project, work, important]
aliases: [work-project, proj-alpha]
cssclass: project-note
cssclasses: [wide, dark]
publish: true
permalink: /projects/alpha
created: 2026-01-01
modified: 2026-01-02
rating: 5
status: active
due: 2026-01-15
completed: false
priority: 1
author: Scott
---

# Project Alpha

Comprehensive project note with all metadata.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()


@pytest.mark.slow
class TestJekyllSchema:
    """Test Jekyll static site schema validation (GitHub Pages)."""

    def test_jekyll_schema_loads(self):
        """Test jekyll schema loads successfully."""
        from reveal.schemas.frontmatter import load_schema
        schema = load_schema('jekyll')
        assert schema is not None
        assert schema['name'] == 'Jekyll Static Site Schema'
        assert 'layout' in schema['required_fields']
        assert 'title' in schema['optional_fields']
        assert 'date' in schema['optional_fields']

    def test_jekyll_valid_post(self):
        """Test validation passes for valid Jekyll post."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
layout: post
title: "My Jekyll Post"
date: 2026-01-03
categories: [blog, tech]
tags: [python, jekyll]
author: Scott
published: true
---

# My Jekyll Post

Content here.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'jekyll'])
            assert result.returncode == 0
            assert 'No issues found' in result.stdout or 'Found 0 issues' in result.stdout or result.stdout.strip() == ''
        finally:
            Path(temp_path).unlink()

    def test_jekyll_missing_required_layout(self):
        """Test validation fails when layout is missing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "Post Without Layout"
date: 2026-01-03
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'jekyll'], check=False)
            assert result.returncode != 0
            assert 'F003' in result.stdout  # Required field missing
            assert 'layout' in result.stdout.lower()
        finally:
            Path(temp_path).unlink()

    @pytest.mark.parametrize('layout_name', ['default', 'post', 'page', 'home'])
    def test_jekyll_valid_common_layouts(self, layout_name):
        """Test validation passes for common Jekyll layouts."""
        content = f'---\nlayout: {layout_name}\ntitle: "Test Page"\n---\n\n# Content\n'
        detections = _validate_schema_api(content, 'jekyll')
        assert detections == [], f"Unexpected violations for layout '{layout_name}': {detections}"

    def test_jekyll_invalid_date_format(self):
        """Test validation fails for invalid date format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
layout: post
title: "My Post"
date: 01/03/2026
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'jekyll'], check=False)
            assert result.returncode != 0
            assert 'F005' in result.stdout  # Custom validation rule
            assert 'YYYY-MM-DD' in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_jekyll_permalink_validation(self):
        """Test permalink must start with /."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
layout: post
title: "My Post"
permalink: posts/my-post
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'jekyll'], check=False)
            assert result.returncode != 0
            assert 'F005' in result.stdout
            assert 'Permalink should start with' in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_jekyll_published_boolean(self):
        """Test published field must be boolean."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
layout: post
title: "My Post"
published: "yes"
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'jekyll'], check=False)
            assert result.returncode != 0
            assert 'F004' in result.stdout or 'F005' in result.stdout  # Type mismatch or validation
        finally:
            Path(temp_path).unlink()

    def test_jekyll_minimal_page(self):
        """Test minimal Jekyll page with only layout."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
layout: default
---

# Minimal Page
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'jekyll'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()

    def test_jekyll_github_pages_example(self):
        """Test real-world GitHub Pages example."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
layout: post
title: "Building with Jekyll on GitHub Pages"
date: 2026-01-03
categories: [tutorial, github]
tags: [jekyll, github-pages, static-sites]
author: Developer
excerpt: "Learn how to build and deploy Jekyll sites on GitHub Pages"
permalink: /posts/jekyll-github-pages/
---

# Building with Jekyll on GitHub Pages

This is a comprehensive guide.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'jekyll'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()


@pytest.mark.slow
class TestMkDocsSchema:
    """Test MkDocs documentation schema validation."""

    def test_mkdocs_schema_loads(self):
        """Test mkdocs schema loads successfully."""
        from reveal.schemas.frontmatter import load_schema
        schema = load_schema('mkdocs')
        assert schema is not None
        assert schema['name'] == 'MkDocs Documentation Schema'
        assert len(schema['required_fields']) == 0  # No required fields
        assert 'title' in schema['optional_fields']
        assert 'hide' in schema['optional_fields']

    def test_mkdocs_no_frontmatter(self):
        """Test MkDocs validation passes with no front matter (all optional)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''# My Documentation Page

This page has no front matter at all.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'mkdocs'], check=False)
            # Should fail with F001 - missing front matter
            assert result.returncode != 0
            assert 'F001' in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_mkdocs_minimal_valid(self):
        """Test minimal valid MkDocs page with minimal front matter."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "Documentation"
---

# Documentation Page

Minimal MkDocs page.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'mkdocs'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()

    def test_mkdocs_full_example(self):
        """Test comprehensive MkDocs example with many fields."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "API Reference"
description: "Complete API documentation for the project"
template: custom.html
icon: material/api
status: new
tags:
  - api
  - reference
  - python
hide:
  - navigation
  - toc
authors:
  - John Doe
  - Jane Smith
date: 2026-01-03
comments: true
---

# API Reference

Documentation content here.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'mkdocs'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()

    def test_mkdocs_material_theme_hide(self):
        """Test Material for MkDocs hide field validation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "Clean Page"
hide:
  - navigation
  - toc
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'mkdocs'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()

    def test_mkdocs_invalid_hide_option(self):
        """Test that invalid hide options are detected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "Test Page"
hide:
  - sidebar
  - header
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'mkdocs'], check=False)
            assert result.returncode != 0
            assert 'F005' in result.stdout
            assert 'navigation' in result.stdout or 'toc' in result.stdout or 'footer' in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_mkdocs_invalid_date_format(self):
        """Test that invalid date format is detected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "Test Page"
date: 01/03/2026
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'mkdocs'], check=False)
            assert result.returncode != 0
            assert 'F005' in result.stdout
            assert 'YYYY-MM-DD' in result.stdout
        finally:
            Path(temp_path).unlink()

    @pytest.mark.parametrize('status_value', ['new', 'deprecated', 'beta', 'experimental'])
    def test_mkdocs_status_values(self, status_value):
        """Test common status values are accepted."""
        content = f'---\ntitle: "Test Page"\nstatus: {status_value}\n---\n\n# Content\n'
        detections = _validate_schema_api(content, 'mkdocs')
        assert detections == [], f"Unexpected violations for status '{status_value}': {detections}"

    def test_mkdocs_real_world_example(self):
        """Test real-world MkDocs example (FastAPI-style docs)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: Tutorial - User Guide
description: A comprehensive guide to using the API
icon: material/school
status: new
tags:
  - tutorial
  - beginner
  - guide
hide:
  - footer
authors:
  - Development Team
date: 2026-01-03
comments: false
---

# Tutorial - User Guide

This tutorial will walk you through the basics.
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'mkdocs'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()


@pytest.mark.slow
class TestSchemaListing:
    """Test that new schemas appear in listing."""

    def test_list_schemas_includes_all_builtin(self):
        """Test list_schemas includes all built-in schemas."""
        from reveal.schemas.frontmatter import list_schemas
        schemas = list_schemas()
        assert 'session' in schemas
        assert 'hugo' in schemas
        assert 'jekyll' in schemas
        assert 'mkdocs' in schemas
        assert 'obsidian' in schemas

    def test_cli_lists_all_schemas_on_error(self):
        """Test CLI error message lists all available schemas."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('# Test\n')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'nonexistent'], check=False)
            assert result.returncode != 0
            assert 'session' in result.stderr
            assert 'hugo' in result.stderr
            assert 'obsidian' in result.stderr
        finally:
            Path(temp_path).unlink()


@pytest.mark.slow
class TestCrossSchemaComparison:
    """Test validation differences between schemas."""

    def test_same_file_different_schemas(self):
        """Test same file validates differently with different schemas."""
        content = '---\ntitle: "Test Document"\ndate: 2026-01-02\n---\n\n# Test\n'

        # Should fail Session validation (missing session_id, topics)
        session_detections = _validate_schema_api(content, 'session')
        assert session_detections, "Expected session validation to find violations"
        codes_or_messages = ' '.join(
            str(getattr(d, 'code', '')) + ' ' + str(getattr(d, 'message', ''))
            for d in session_detections
        )
        assert 'session_id' in codes_or_messages or 'topics' in codes_or_messages, (
            f"Expected session_id or topics violation, got: {codes_or_messages}"
        )

        # Should pass Hugo validation (has required title and date)
        hugo_detections = _validate_schema_api(content, 'hugo')
        assert hugo_detections == [], f"Hugo should pass, got: {hugo_detections}"

        # Should pass Obsidian validation (no required fields)
        obsidian_detections = _validate_schema_api(content, 'obsidian')
        assert obsidian_detections == [], f"Obsidian should pass, got: {obsidian_detections}"


@pytest.mark.slow
class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_hugo_date_with_time(self):
        """Test Hugo accepts date with time (RFC3339)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "Post with Time"
date: 2026-01-02T15:30:00Z
---

# Content
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()

    def test_obsidian_tags_single_string(self):
        """Test Obsidian rejects single string tags (should be list)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
tags: single-tag
---

# Note
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'obsidian'], check=False)
            # Should fail type check (tags should be list)
            assert result.returncode != 0
            assert 'F004' in result.stdout  # Wrong type
        finally:
            Path(temp_path).unlink()

    def test_hugo_unicode_in_title(self):
        """Test Hugo handles unicode in title."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write('''---
title: "測試文章 🚀"
date: 2026-01-02
---

# Unicode Test
''')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'hugo'])
            assert result.returncode == 0
        finally:
            Path(temp_path).unlink()
