# Changelog

All notable changes to reveal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2025-11-23

### Added
- **`--version` flag** to show current version
- **`--list-supported` flag** (`-l` shorthand) to display all supported file types with icons
- **Cross-platform compatibility checker** (`check_cross_platform.sh`) - automated audit tool
- **Comprehensive documentation:**
  - `CHANGELOG.md` - Complete version history
  - `CROSS_PLATFORM.md` - Windows/Linux/macOS compatibility guide
  - `IMPROVEMENTS_SUMMARY.md` - Detailed improvement tracking
- **Enhanced help text** with organized examples (Directory, File, Element, Formats, Discovery)
- **11 new tests** in `test_main_cli.py` covering all new features
- **Validation script** `validate_v0.4.0.sh` (updated from v0.3.0)

### Changed
- **Better error messages** with actionable hints:
  - Shows full path and extension for unsupported files
  - Suggests `--list-supported` to see supported types
  - Links to GitHub for feature requests
- **Improved help output:**
  - GDScript examples included
  - Better organized examples by category
  - Clear explanations of all flags
  - Professional tagline about filename:line integration
- **Updated README:**
  - Version badge: v0.3.0 (was v0.2.0)
  - Added GDScript to features and examples
  - Added new flags to Optional Flags section
- **Updated INSTALL.md:**
  - PyPI installation shown first
  - New verification commands (--version, --list-supported)
  - Removed outdated --level references
  - Updated CI/CD examples

### Fixed
- Documentation consistency (removed all outdated --level references)
- README version accuracy

## [0.3.0] - 2025-11-23

### Added
- **GDScript analyzer** for Godot game engine files (.gd)
  - Extracts classes, functions, signals, and variables
  - Supports type hints and return types
  - Handles export variables and onready modifiers
  - Inner class support
- **Windows UTF-8/emoji support** - fixes console encoding issues on Windows
- Comprehensive validation samples for all 10 file types
- Validation samples: `calculator.rs` (Rust), `server.go` (Go), `analysis.ipynb` (Jupyter), `player.gd` (GDScript)

### Changed
- Modernized Jupyter analyzer for v0.2.0+ architecture
- Updated validation samples to be Windows-compatible
- Removed archived v0.1 code (4,689 lines cleaned up)

### Fixed
- Windows console encoding crash with emoji/unicode characters
- Jupyter analyzer compatibility with new architecture
- Hardcoded Unix paths in validation samples

### Contributors
- @Huzza27 - Windows UTF-8 encoding fix (PR #5)
- @scottsen - GDScript support and test coverage

## [0.2.0] - 2025-11-23

### Added
- Clean redesign with simplified architecture
- TreeSitter-based analyzers for Rust, Go
- Markdown, JSON, YAML analyzers
- Comprehensive validation suite (15 automated tests)
- `--format=grep` option for pipeable output
- `--format=json` option for programmatic access
- `--meta` flag for metadata-only view
- `--depth` flag for directory tree depth control

### Changed
- Complete architecture redesign (500 lines core, 10-50 lines per analyzer)
- Simplified CLI interface - removed 4-level progressive disclosure
- New element extraction model (positional argument instead of --level)
- Improved filename:line format throughout

### Removed
- Old 4-level `--level` system (replaced with simpler model)
- Legacy plugin YAML configs (moved to decorator-based registration)

## [0.1.0] - 2025-11-22

### Added
- Initial release
- Basic file exploration
- Python analyzer
- Plugin architecture
- Progressive disclosure (4 levels)
- Basic CLI interface

---

## Version History Summary

- **0.3.0** - GDScript + Windows Support
- **0.2.0** - Clean Redesign
- **0.1.0** - Initial Release

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding new features and file types.

## Links

- **GitHub**: https://github.com/scottsen/reveal
- **PyPI**: https://pypi.org/project/reveal-cli/
- **Issues**: https://github.com/scottsen/reveal/issues
