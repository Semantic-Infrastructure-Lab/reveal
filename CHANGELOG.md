# Changelog

All notable changes to reveal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2025-11-23

### Added
- **Nginx configuration analyzer** (.conf) - Web server config analysis
  - Extracts server blocks with ports and server names
  - Identifies location blocks with routing targets (proxy_pass, static roots)
  - Detects upstream blocks for load balancing
  - Captures header comments with deployment status
  - Line-accurate navigation to config sections
  - Supports HTTP→HTTPS redirect patterns
  - Cross-platform compatible

## [0.5.0] - 2025-11-23

### Added
- **JavaScript analyzer** (.js) - Full ES6+ support via tree-sitter
  - Extracts function declarations, arrow functions, classes
  - Supports import/export statements
  - Handles async functions and object methods
  - Cross-platform compatible (Windows/Linux/macOS)

- **TypeScript analyzer** (.ts, .tsx) - Full TypeScript support via tree-sitter
  - Extracts functions with type annotations
  - Supports class definitions and interfaces
  - React/TSX component support (.tsx files)
  - Type definitions and return types
  - Cross-platform compatible (Windows/Linux/macOS)

- **Bash/Shell script analyzer** (.sh, .bash) - DevOps script support via tree-sitter
  - Extracts function definitions (both `function name()` and `name()` syntax)
  - Cross-platform analysis (parses bash syntax on any OS)
  - Does NOT execute scripts, only analyzes syntax
  - Works with WSL, Git Bash, and native Unix shells
  - Custom `_get_function_name()` implementation for bash 'word' node types

- **12 comprehensive tests** in `test_new_analyzers.py`:
  - JavaScript: functions, classes, imports, UTF-8 handling
  - TypeScript: typed functions, classes, interfaces, TSX/React components
  - Bash: function extraction, complex scripts, cross-platform compatibility
  - Cross-platform UTF-8 validation for all three analyzers

### Changed
- **File type count: 10 → 15** supported file types
  - JavaScript (.js)
  - TypeScript (.ts, .tsx) - 2 extensions
  - Bash (.sh, .bash) - 2 extensions

- **Updated analyzers/__init__.py** to register new analyzers
- **Fixed test_main_cli.py** version assertion to use regex pattern instead of hardcoded version

### Technical Details

**JavaScript Support:**
- Tree-sitter language: `javascript`
- Node types: function_declaration, class_declaration, import_statement
- Handles modern ES6+ syntax (arrow functions, classes, modules)

**TypeScript Support:**
- Tree-sitter language: `typescript`
- Supports both .ts and .tsx (React) files
- Extracts type annotations and interfaces
- Handles generic types and complex TypeScript features

**Bash Support:**
- Tree-sitter language: `bash`
- Custom implementation: Bash uses `word` for function names, not `identifier`
- Overrides `_get_function_name()` to handle bash-specific AST structure
- Supports both `function deploy() {}` and `deploy() {}` syntaxes

**Cross-Platform Strategy:**
- JavaScript/TypeScript: Universal web languages, native cross-platform support
- Bash: Analyzes syntax only (doesn't execute), works on Windows via WSL/Git Bash
- All analyzers tested on UTF-8 content with emoji and multi-byte characters

**Real-World Validation:**
- Tested on SDMS platform codebase
- JavaScript: Extracted classes from pack-builder.js files
- Bash: Extracted 5+ functions from deploy-container.sh
- All UTF-8 characters (emoji, special symbols) handled correctly

### Windows Compatibility
All new analyzers are fully Windows-compatible:
- **JavaScript/TypeScript:** Native cross-platform support
- **Bash:** Syntax analysis works on Windows (common in Git Bash, WSL, Docker workflows)
- No execution required, only parsing

**Future Windows Support:**
- PowerShell (.ps1) - Not yet available in tree-sitter-languages
- Batch files (.bat, .cmd) - Not yet available in tree-sitter-languages

## [0.4.1] - 2025-11-23

### Fixed
- **CRITICAL: TreeSitter UTF-8 byte offset handling** - Fixed function/class/import name truncation bug
  - GitHub Issues #6, #7, #8: Function names, class names, and import statements were truncated or corrupted
  - Root cause: Tree-sitter uses byte offsets but we were slicing Unicode strings
  - Multi-byte UTF-8 characters (emoji, non-Latin scripts) caused byte/character offset mismatch
  - Solution: Convert to bytes for slicing, then decode back to string
  - Affected all tree-sitter languages (Python, Rust, Go, GDScript, etc.)
  - Fixed in `reveal/treesitter.py:_get_node_text()`
- **Test assertion:** Updated version test to expect 0.4.0 (was incorrectly testing for 0.3.0)

### Added
- **4 comprehensive UTF-8 regression tests** in `test_treesitter_utf8.py`:
  - Test function names with emoji in docstrings
  - Test class names with multi-byte characters
  - Test imports with Unicode strings
  - Test complex Unicode throughout file (multiple languages, extensive emoji)
- Extensive code comments explaining UTF-8 byte offset handling

### Technical Details
**Bug reproduction:**
- Files with multi-byte UTF-8 characters before function/class/import definitions
- Tree-sitter returns byte offset 100, but string character offset is 97 (if 3-byte emoji present)
- Slicing `string[100:]` starts too far, losing first few characters

**Examples of bugs fixed:**
- ❌ Before: `test_function_name` → `st_function_name` (missing "te")
- ✅ After: `test_function_name` (complete)
- ❌ Before: `import numpy as np` → `rt numpy as np\nimp` (garbled)
- ✅ After: `import numpy as np` (clean)
- ❌ Before: `TestClassName` → `tClassName` (truncated)
- ✅ After: `TestClassName` (complete)

**Impact:**
- All tree-sitter-based analyzers now handle Unicode correctly
- Python, Rust, Go, GDScript all benefit from this fix
- Particularly important for codebases with emoji in docstrings or non-Latin comments

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
