---
title: Reveal Installation Guide
type: documentation
category: installation
date: 2026-10-24
---

# Installation Guide

## Quick Install (Recommended)

**From PyPI (stable release):**
```bash
pip install reveal-cli
```

That's it! The `reveal` command is now available globally.

## Verify Installation

```bash
reveal --version          # Check version
reveal --list-supported   # See supported file types
reveal README.md          # Try on any file
```

## Alternative Methods

### From Source (Development)

```bash
git clone https://github.com/Semantic-Infrastructure-Lab/reveal.git
cd reveal
pip install -e .
```

The `-e` flag installs in "editable" mode - changes to the code take effect immediately.
To install the latest development version without cloning:
`pip install git+https://github.com/Semantic-Infrastructure-Lab/reveal.git`.

### Specific Version

```bash
pip install reveal-cli==<version>
```

### Using pipx (Isolated Environment)

```bash
pipx install reveal-cli
```

## Requirements

- **Python:** 3.10 or higher
- **Dependencies:** Automatically installed (PyYAML, rich)

## What's Included by Default

Just `pip install reveal-cli` gives you everything:

**Languages (51 — run `reveal --languages` for the live breakdown):**
- Explicit analyzers: Python, JavaScript, TypeScript, Rust, Go, C, C++, C#, Java, Ruby, PHP, Kotlin, Swift, Dart, Zig, Scala, Lua, GDScript, Bash, SQL, and more
- Markdown, JSON, JSONL, YAML, TOML, HCL/Terraform, GraphQL, Protobuf
- Nginx configs, Dockerfiles
- Office documents: Word (.docx), Excel (.xlsx), PowerPoint (.pptx)
- LibreOffice: Writer (.odt), Calc (.ods), Impress (.odp)
- All other tree-sitter grammars work immediately as a structure-only fallback - no extra installation needed, though the underlying `tree-sitter-language-pack` dependency downloads its grammar bundle from GitHub the first time it's used on a machine — see [Network Requirements](#network-requirements) below.

**URI Adapters (run `reveal --adapters` for the live, current list):**
- `help://` - Self-documenting help system
- `env://` - Environment variable inspection
- `ast://` - Code queries and semantic analysis
- `json://` - JSON navigation with path access
- `python://` - Python runtime inspection and diagnostics
- `reveal://` - Self-inspection and validation
- `stats://` - Code quality metrics and hotspot detection
- ...plus `calls://`, `git://`, `imports://`, `claude://`, `codex://`, `diff://`, `depends://`, and more

## Optional Features

The base install leaves out a few third-party packages, each behind an extra:
`git` (the `git://` adapter), `database` (`mysql://`), `dns` and `whois` (parts of
`domain://`), `mcp` (the `reveal-mcp` server), `html`, `powerpivot`, `xlsx` and `dev`, plus `all`
(every runtime extra except `powerpivot`, which adds ~100 MB; see the install guide).

```bash
pip install "reveal-cli[git]"            # one extra
pip install "reveal-cli[git,database]"   # several
pip install "reveal-cli[all]"            # every adapter + reveal-mcp (not powerpivot)
```

What each extra unlocks, and the error you get without it, is in the
[install guide](reveal/docs/guides/INSTALL_GUIDE.md#optional-extras) -- also searchable
from the CLI: `reveal help://install` or `reveal 'help://search?search=extras'`.

## Network Requirements

`pip install reveal-cli` needs PyPI. After that, reveal only touches the network for
explicitly network-oriented features and a daily PyPI update check
(`REVEAL_NO_UPDATE_CHECK=1` disables it).

**Air-gapped or restricted hosts:** the first parse of a language not yet parsed on the machine
downloads a tree-sitter grammar bundle from GitHub Releases. Pre-seed it on a connected machine:

```bash
reveal offline --languages python,javascript,go   # or `reveal offline` for every grammar
```

The egress allowlist, cache location, failure behavior and the full container recipe are in the
[install guide](reveal/docs/guides/INSTALL_GUIDE.md#network-requirements)
(`reveal help://install/full`).

## Troubleshooting

### Permission Denied

If you get permission errors, try:
```bash
pip install --user reveal-cli
```

### Command Not Found

If `reveal` is not found after installation, add to your PATH:
```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"
```

Then reload your shell:
```bash
source ~/.bashrc  # or source ~/.zshrc
```

On a locked-down Windows machine where the `reveal.exe` launcher is blocked, run
`python -m reveal` instead.

### Upgrade to Latest

```bash
pip install --upgrade reveal-cli
```

### Uninstall

```bash
pip uninstall reveal-cli
```

## Custom Analyzers

Drop a `*_analyzer.py` file into `.reveal/analyzers/` (one project) or `~/.reveal/plugins/`
(all projects) and reveal loads it at startup. The file format and a worked example are in the
[Configuration Guide](reveal/docs/guides/CONFIGURATION_GUIDE.md) (also `reveal help://config`).

## For Projects

Add `reveal-cli` to `requirements.txt`, or to `dependencies` under `[project]` in
`pyproject.toml`:

```txt
reveal-cli
```

## CI/CD Integration

### GitHub Actions

```yaml
- name: Install reveal
  run: pip install reveal-cli

- name: Analyze files
  run: |
    reveal src/main.py
    reveal config.yaml
    reveal src/main.py main --format=json  # Extract main function as JSON
```

## Next Steps

After installation:

1. **Try it:** `reveal --help`
2. **Explore a file:** `reveal README.md`
3. **Extract an element:** `reveal app.py function_name`
4. **Read docs:** See [README](reveal/docs/README.md) for examples
5. **Contribute:** [Contributing Guide](CONTRIBUTING.md)

## Getting Help

- **Issues:** https://github.com/Semantic-Infrastructure-Lab/reveal/issues
- **Discussions:** https://github.com/Semantic-Infrastructure-Lab/reveal/discussions
- **Documentation:** https://github.com/Semantic-Infrastructure-Lab/reveal/tree/main/reveal/docs

---

**Having trouble?** Open an issue and we'll help!
