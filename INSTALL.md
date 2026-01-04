# Installation Guide

## Quick Install (Recommended)

**From PyPI (stable release):**
```bash
pip install reveal-cli
```

**From GitHub (latest development):**
```bash
pip install git+https://github.com/Semantic-Infrastructure-Lab/reveal.git
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

### Specific Version

```bash
# Install specific tag/release
pip install git+https://github.com/Semantic-Infrastructure-Lab/reveal.git@v0.1.0

# Install specific branch
pip install git+https://github.com/Semantic-Infrastructure-Lab/reveal.git@main
```

### Using pipx (Isolated Environment)

```bash
# Install with pipx for isolated environment
pipx install git+https://github.com/Semantic-Infrastructure-Lab/reveal.git
```

## Requirements

- **Python:** 3.10 or higher
- **Dependencies:** Automatically installed (PyYAML, rich)

## What's Included by Default

Just `pip install reveal-cli` gives you everything:

**Languages (25+ built-in):**
- Python, JavaScript, TypeScript, Rust, Go, C, C++, C#, Java
- GDScript, Bash, Shell Scripts, Jupyter Notebooks
- Markdown, JSON, JSONL, YAML, TOML
- Nginx configs, Dockerfiles
- Office documents: Word (.docx), Excel (.xlsx), PowerPoint (.pptx)
- LibreOffice: Writer (.odt), Calc (.ods), Impress (.odp)

**Tree-sitter support (50+ languages):**
All tree-sitter languages work immediately - no extra installation needed since v0.8.0 (Nov 2025).

**URI Adapters (7 included):**
- `help://` - Self-documenting help system
- `env://` - Environment variable inspection
- `ast://` - Code queries and semantic analysis
- `json://` - JSON navigation with path access
- `python://` - Python runtime inspection and diagnostics
- `reveal://` - Self-inspection and validation
- `stats://` - Code quality metrics and hotspot detection

## Optional Features

### MySQL Database Inspection

For database health inspection with the `mysql://` adapter:

```bash
pip install reveal-cli[database]
```

**What you get:**
- MySQL database health monitoring and diagnostics
- Industry-standard DBA tuning ratios (table scans, thread cache efficiency, temp tables)
- Index usage analysis (most used indexes, unused indexes)
- Slow query detection and analysis (last 24 hours)
- InnoDB buffer pool metrics and lock information

**Examples:**
```bash
reveal mysql://localhost                    # Health overview
reveal mysql://localhost/performance        # Performance metrics + DBA tuning ratios
reveal mysql://localhost/indexes            # Index usage analysis
reveal mysql://localhost/slow-queries       # Slow query analysis (last 24h)
reveal mysql://localhost/innodb             # InnoDB buffer pool and locks
```

### Development Tools

For contributors:

```bash
pip install reveal-cli[dev]
```

**Includes:** pytest, pytest-cov, black, ruff

### Installing Multiple Extras

```bash
pip install reveal-cli[database,dev]
```

## Migration Note

**If you previously used `[treesitter]` extra:**

Tree-sitter is now included by default (since v0.8.0, Nov 2025). You can safely remove `[treesitter]` from your install commands - it's no longer needed, but old commands still work for backward compatibility.

**Example:**
```bash
# Old (still works, but unnecessary)
pip install reveal-cli[treesitter]

# New (recommended)
pip install reveal-cli
```

## Troubleshooting

### Permission Denied

If you get permission errors, try:
```bash
pip install --user git+https://github.com/Semantic-Infrastructure-Lab/reveal.git
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

### Upgrade to Latest

```bash
pip install --upgrade git+https://github.com/Semantic-Infrastructure-Lab/reveal.git
```

### Uninstall

```bash
pip uninstall reveal-cli
```

## Custom Plugin Directory

Create custom plugins in `~/.config/reveal/plugins/`:

```bash
mkdir -p ~/.config/reveal/plugins
cd ~/.config/reveal/plugins

# Create your plugin
cat > rust.yaml << 'EOF'
extension: .rs
name: Rust Source
icon: 🦀
levels:
  0: {name: metadata, description: "File stats"}
  1: {name: structure, description: "Code structure"}
  2: {name: preview, description: "Code preview"}
  3: {name: full, description: "Complete source"}
EOF
```

Custom plugins are automatically loaded alongside built-in plugins.

## For Projects

Add to `requirements.txt`:
```txt
reveal-cli @ git+https://github.com/Semantic-Infrastructure-Lab/reveal.git
```

Or `pyproject.toml`:
```toml
[project.dependencies]
reveal-cli = {git = "https://github.com/Semantic-Infrastructure-Lab/reveal.git"}
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
4. **Read docs:** See [README](README.md) for examples
5. **Contribute:** [Contributing Guide](CONTRIBUTING.md)

## Getting Help

- **Issues:** https://github.com/Semantic-Infrastructure-Lab/reveal/issues
- **Discussions:** https://github.com/Semantic-Infrastructure-Lab/reveal/discussions
- **Documentation:** https://github.com/Semantic-Infrastructure-Lab/reveal/tree/main/docs

---

**Having trouble?** Open an issue and we'll help!
