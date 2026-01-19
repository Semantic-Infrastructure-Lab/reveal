---
title: Reveal Security Policy
type: documentation
category: security
date: 2025-12-01
---

# Security Policy

## Reporting Security Issues

If you discover a security vulnerability, please email: scottsen@users.noreply.github.com

**Please do not open public issues for security vulnerabilities.**

## What Reveal Does

Reveal is a local code analysis tool that:
- Reads files from your filesystem (read-only)
- Parses code using tree-sitter
- Displays structure and metrics
- **Does not** send data over the network (except optional PyPI version check)
- **Does not** execute code from analyzed files

## Security Features

- ✅ Read-only file access
- ✅ No code execution from analyzed files
- ✅ Minimal dependencies (pyyaml, rich, tree-sitter)
- ✅ Path traversal protection via `pathlib`
- ✅ UTF-8 encoding with error handling

Keep updated with: `pip install --upgrade reveal-cli`
