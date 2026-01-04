"""Tests for built-in schemas (Hugo, Jekyll, MkDocs, Obsidian).

Tests schema validation with real-world examples and edge cases.
"""

import pytest
import tempfile
import subprocess
from pathlib import Path


def run_reveal(args, check=True):
    """Helper to run reveal CLI and capture output.

    Args:
        args: List of command-line arguments
        check: If True, raise CalledProcessError on non-zero exit

    Returns:
        subprocess.CompletedProcess result
    """
    cmd = ['reveal'] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=False
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )
    return result


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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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

    def test_jekyll_valid_common_layouts(self):
        """Test validation passes for common Jekyll layouts."""
        layouts = ['default', 'post', 'page', 'home']

        for layout_name in layouts:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(f'''---
layout: {layout_name}
title: "Test Page"
---

# Content
''')
                temp_path = f.name

            try:
                result = run_reveal([temp_path, '--validate-schema', 'jekyll'])
                assert result.returncode == 0, f"Failed for layout: {layout_name}"
            finally:
                Path(temp_path).unlink()

    def test_jekyll_invalid_date_format(self):
        """Test validation fails for invalid date format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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

    def test_mkdocs_status_values(self):
        """Test common status values are accepted."""
        statuses = ['new', 'deprecated', 'beta', 'experimental']

        for status_value in statuses:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(f'''---
title: "Test Page"
status: {status_value}
---

# Content
''')
                temp_path = f.name

            try:
                result = run_reveal([temp_path, '--validate-schema', 'mkdocs'])
                assert result.returncode == 0, f"Failed for status: {status_value}"
            finally:
                Path(temp_path).unlink()

    def test_mkdocs_real_world_example(self):
        """Test real-world MkDocs example (FastAPI-style docs)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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


class TestSchemaListing:
    """Test that new schemas appear in listing."""

    def test_list_schemas_includes_all_builtin(self):
        """Test list_schemas includes all built-in schemas."""
        from reveal.schemas.frontmatter import list_schemas
        schemas = list_schemas()
        assert 'beth' in schemas
        assert 'hugo' in schemas
        assert 'jekyll' in schemas
        assert 'mkdocs' in schemas
        assert 'obsidian' in schemas

    def test_cli_lists_all_schemas_on_error(self):
        """Test CLI error message lists all available schemas."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# Test\n')
            temp_path = f.name

        try:
            result = run_reveal([temp_path, '--validate-schema', 'nonexistent'], check=False)
            assert result.returncode != 0
            assert 'beth' in result.stderr
            assert 'hugo' in result.stderr
            assert 'obsidian' in result.stderr
        finally:
            Path(temp_path).unlink()


class TestCrossSchemaComparison:
    """Test validation differences between schemas."""

    def test_same_file_different_schemas(self):
        """Test same file validates differently with different schemas."""
        # A file with just title and date
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''---
title: "Test Document"
date: 2026-01-02
---

# Test
''')
            temp_path = f.name

        try:
            # Should fail Beth validation (missing session_id, beth_topics)
            beth_result = run_reveal([temp_path, '--validate-schema', 'beth'], check=False)
            assert beth_result.returncode != 0
            assert 'session_id' in beth_result.stdout or 'beth_topics' in beth_result.stdout

            # Should pass Hugo validation (has required title and date)
            hugo_result = run_reveal([temp_path, '--validate-schema', 'hugo'])
            assert hugo_result.returncode == 0

            # Should pass Obsidian validation (no required fields)
            obsidian_result = run_reveal([temp_path, '--validate-schema', 'obsidian'])
            assert obsidian_result.returncode == 0
        finally:
            Path(temp_path).unlink()


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_hugo_date_with_time(self):
        """Test Hugo accepts date with time (RFC3339)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
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
