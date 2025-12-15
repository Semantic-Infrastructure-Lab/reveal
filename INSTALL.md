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

- **Python:** 3.8 or higher
- **Dependencies:** Automatically installed (PyYAML, rich)

## Optional Features

### Tree-sitter Language Support

For advanced language analysis (Rust, C#, Go, Java, TypeScript, C++, and 40+ more):

```bash
# Install with tree-sitter support
pip install 'git+https://github.com/Semantic-Infrastructure-Lab/reveal.git#egg=reveal-cli[treesitter]'

# Or upgrade existing install
pip install --upgrade 'git+https://github.com/Semantic-Infrastructure-Lab/reveal.git#egg=reveal-cli[treesitter]'
```

**What you get:**
- Rust analyzer (functions, structs, enums, traits, impls, modules)
- C# analyzer (classes, methods, properties, namespaces, interfaces)
- Easy to add more languages (Go, Java, TypeScript, etc.) - see PLUGIN_GUIDE.md

**Without tree-sitter:** Rust/C# files fall back to text analyzer (still works, just less structured)

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
