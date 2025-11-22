# Publishing to PyPI

This document explains how to publish `reveal-cli` to PyPI.

## Prerequisites

1. PyPI account: https://pypi.org/account/register/
2. API token from PyPI: https://pypi.org/manage/account/token/
3. GitHub repository secrets configured with `PYPI_API_TOKEN`

## Automated Publishing (Recommended)

Publishing happens automatically via GitHub Actions when you create a release:

### Steps:

1. **Update version in `pyproject.toml`**
   ```toml
   [project]
   version = "0.2.0"  # Update this
   ```

2. **Commit and push changes**
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.2.0"
   git push
   ```

3. **Create a GitHub release**
   ```bash
   # Using GitHub CLI
   gh release create v0.2.0 --title "v0.2.0" --notes "Release notes here"

   # Or via GitHub web interface:
   # Go to: https://github.com/scottsen/reveal/releases/new
   # Tag: v0.2.0
   # Title: v0.2.0
   # Description: Release notes
   # Click "Publish release"
   ```

4. **GitHub Actions automatically:**
   - Builds the package
   - Runs quality checks
   - Publishes to PyPI

5. **Verify publication**
   ```bash
   # Wait a few minutes, then:
   pip install reveal-cli==0.2.0
   reveal --help
   ```

## Manual Publishing (For Testing)

### Test PyPI First (Recommended)

1. **Get TestPyPI token**: https://test.pypi.org/manage/account/token/

2. **Build the package**
   ```bash
   python -m pip install --upgrade build twine
   python -m build
   ```

3. **Check the build**
   ```bash
   twine check dist/*
   ```

4. **Upload to TestPyPI**
   ```bash
   twine upload --repository testpypi dist/*
   # Username: __token__
   # Password: <your TestPyPI token>
   ```

5. **Test installation**
   ```bash
   pip install --index-url https://test.pypi.org/simple/ reveal-cli
   reveal --help
   ```

### Production PyPI

1. **Get PyPI token**: https://pypi.org/manage/account/token/

2. **Build and upload**
   ```bash
   rm -rf dist/
   python -m build
   twine check dist/*
   twine upload dist/*
   # Username: __token__
   # Password: <your PyPI token>
   ```

3. **Verify**
   ```bash
   pip install reveal-cli
   reveal --help
   ```

## Setting up GitHub Secrets

To enable automated publishing:

1. Go to: https://github.com/scottsen/reveal/settings/secrets/actions
2. Click "New repository secret"
3. Name: `PYPI_API_TOKEN`
4. Value: Your PyPI API token (starts with `pypi-`)
5. Click "Add secret"

## Troubleshooting

### Build fails with "plugins not found"

Ensure `MANIFEST.in` includes:
```
include plugins/*.yaml
```

And `pyproject.toml` has:
```toml
[tool.setuptools.packages.find]
include = ["reveal*", "plugins"]

[tool.setuptools.package-data]
plugins = ["*.yaml", "*.yml"]
```

### Upload fails with "File already exists"

You can't replace a version on PyPI. You must:
1. Increment the version in `pyproject.toml`
2. Create a new release

### Import errors after installation

Check that plugins are in the wheel:
```bash
python -m zipfile -l dist/reveal_cli-*.whl | grep plugins
```

## Version Numbering

We use semantic versioning (semver):
- `MAJOR.MINOR.PATCH` (e.g., `1.2.3`)
- Major: Breaking changes
- Minor: New features, backward compatible
- Patch: Bug fixes

Examples:
- `0.1.0` → `0.1.1` - Bug fix
- `0.1.1` → `0.2.0` - New GDScript support
- `0.9.0` → `1.0.0` - First stable release

## Checklist Before Release

- [ ] All tests passing
- [ ] Version updated in `pyproject.toml`
- [ ] CHANGELOG.md updated
- [ ] README.md up to date
- [ ] Test build locally: `python -m build`
- [ ] Check wheel contents: `python -m zipfile -l dist/*.whl`
- [ ] Plugins included in build
- [ ] GitHub Actions workflow configured
- [ ] PyPI token added to GitHub secrets

## Resources

- PyPI: https://pypi.org/
- TestPyPI: https://test.pypi.org/
- Python Packaging Guide: https://packaging.python.org/
- Twine docs: https://twine.readthedocs.io/
