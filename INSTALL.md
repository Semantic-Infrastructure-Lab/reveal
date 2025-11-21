# Installation Guide

## Quick Install (Recommended)

**One command:**
```bash
pip install git+https://github.com/scottsen/reveal.git
```

That's it! The `reveal` command is now available globally.

## Verify Installation

```bash
reveal --help
reveal README.md  # Try on any file
```

## Alternative Methods

### From Source (Development)

```bash
git clone https://github.com/scottsen/reveal.git
cd reveal
pip install -e .
```

The `-e` flag installs in "editable" mode - changes to the code take effect immediately.

### Specific Version

```bash
# Install specific tag/release
pip install git+https://github.com/scottsen/reveal.git@v0.1.0

# Install specific branch
pip install git+https://github.com/scottsen/reveal.git@main
```

### Using pipx (Isolated Environment)

```bash
# Install with pipx for isolated environment
pipx install git+https://github.com/scottsen/reveal.git
```

## Requirements

- **Python:** 3.8 or higher
- **Dependencies:** Automatically installed (PyYAML, rich)

## Troubleshooting

### Permission Denied

If you get permission errors, try:
```bash
pip install --user git+https://github.com/scottsen/reveal.git
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
pip install --upgrade git+https://github.com/scottsen/reveal.git
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
reveal-cli @ git+https://github.com/scottsen/reveal.git
```

Or `pyproject.toml`:
```toml
[project.dependencies]
reveal-cli = {git = "https://github.com/scottsen/reveal.git"}
```

## CI/CD Integration

### GitHub Actions

```yaml
- name: Install reveal
  run: pip install git+https://github.com/scottsen/reveal.git

- name: Analyze files
  run: |
    reveal src/main.py --level 1
    reveal config.yaml --level 2
```

## Next Steps

After installation:

1. **Try it:** `reveal --help`
2. **Explore a file:** `reveal README.md --level 1`
3. **Read docs:** [Plugin Guide](docs/PLUGIN_GUIDE.md)
4. **Contribute:** [Contributing Guide](CONTRIBUTING.md)

## Getting Help

- **Issues:** https://github.com/scottsen/reveal/issues
- **Discussions:** https://github.com/scottsen/reveal/discussions
- **Documentation:** https://github.com/scottsen/reveal/tree/main/docs

---

**Having trouble?** Open an issue and we'll help!
