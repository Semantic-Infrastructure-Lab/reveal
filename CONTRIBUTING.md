# Contributing to reveal

Thank you for your interest in contributing to `reveal`! This project is designed to grow through community contributions, especially new file type plugins.

## Ways to Contribute

### 1. Add New File Type Plugins 🔌

**This is the easiest and most impactful way to contribute!**

Create a YAML file in `plugins/` that defines how to reveal your file type:

```yaml
# plugins/rust.yaml
extension: .rs
name: Rust Source
description: Rust source files
icon: 🦀

levels:
  0: {name: metadata, description: "File stats"}
  1: {name: structure, analyzer: rust_structure}
  2: {name: preview, analyzer: rust_preview}
  3: {name: full, description: "Complete source"}

features: {grep: true, context: true, paging: true}
```

Then implement the analyzer in `reveal/analyzers/rust_analyzer.py`.

See [docs/PLUGIN_GUIDE.md](docs/PLUGIN_GUIDE.md) for details.

### 2. Improve Existing Analyzers

- Make them faster
- Add more detailed structure extraction
- Improve output formatting
- Add better error handling

### 3. Add Features

- Syntax highlighting
- Export to different formats
- Integration with editors/IDEs
- Performance improvements

### 4. Documentation

- Improve README
- Write tutorials
- Add examples
- Document AI integration patterns

### 5. Bug Reports & Feature Requests

Open an issue with:
- Clear description
- Steps to reproduce (for bugs)
- Expected vs actual behavior
- Your environment (OS, Python version)

## Development Setup

```bash
# Clone and install in development mode
cd ~/src/projects/reveal
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black reveal/
ruff check reveal/

# Run specific test
pytest tests/test_plugin_loader.py -v
```

## Plugin Development Workflow

1. **Create YAML definition** in `plugins/your-filetype.yaml`
2. **Implement analyzer** (if needed) in `reveal/analyzers/`
3. **Add tests** in `tests/test_your_filetype.py`
4. **Update documentation** - add to README's supported types
5. **Submit PR** with example files

## Code Style

- **Python**: Follow PEP 8, use `black` for formatting
- **Line length**: 100 characters
- **Type hints**: Use them for public APIs
- **Docstrings**: Google style
- **Comments**: Explain *why*, not *what*

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=reveal --cov-report=html

# Test specific analyzer
pytest tests/test_python_analyzer.py -v
```

### Writing Tests

```python
def test_python_structure_analyzer():
    """Test Python structure analysis"""
    from reveal.analyzers.python_analyzer import PythonStructureAnalyzer

    analyzer = PythonStructureAnalyzer()
    result = analyzer.analyze("test_files/sample.py")

    assert "imports" in result
    assert len(result["classes"]) == 2
    assert "UserManager" in result["classes"]
```

## Commit Messages

Use conventional commits:

```
feat: add Rust file type plugin
fix: handle binary files in metadata analyzer
docs: improve plugin development guide
test: add C header analyzer tests
refactor: simplify plugin loader logic
```

## Pull Request Process

1. **Fork** the repository
2. **Create branch**: `git checkout -b feature/rust-plugin`
3. **Make changes** with clear commits
4. **Add tests** that pass
5. **Update docs** if needed
6. **Submit PR** with clear description

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] New file type plugin
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Performance improvement

## Testing
- [ ] Tests added/updated
- [ ] All tests pass
- [ ] Tested with example files

## Checklist
- [ ] Code follows style guide
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

## Community

- **Questions?** Open a discussion
- **Ideas?** Open an issue with `[Idea]` tag
- **Stuck?** Ask for help in your PR

## Priority Areas

**Most wanted plugins:**
- Excel/Spreadsheets (.xlsx, .csv)
- Jupyter Notebooks (.ipynb)
- TypeScript (.ts, .tsx)
- Go (.go)
- Rust (.rs)
- SQL (.sql)
- Terraform (.tf)
- Docker (Dockerfile)
- Shell scripts (.sh, .bash)

**Most wanted features:**
- Syntax highlighting
- Language server protocol integration
- Export to JSON/markdown
- Recursive directory exploration
- GitHub Action integration

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors will be listed in:
- README.md contributors section
- Release notes
- Plugin credits (for plugin authors)

---

**Thank you for making `reveal` better for the agentic AI community!** 🎉
