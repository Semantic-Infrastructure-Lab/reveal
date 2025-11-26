# Changelog

All notable changes to reveal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`--stdin` flag** - Unix pipeline workflows! Read file paths from stdin (one per line)
  - Enables composability with find, git, ls, and other Unix tools
  - Works with all existing flags: `--god`, `--outline`, `--format`, etc.
  - Graceful error handling: skips missing files and directories with warnings
  - Perfect for dynamic file selection and CI/CD workflows
  - Examples:
    - `find src/ -name "*.py" | reveal --stdin --god` - Find complex code in Python files
    - `git diff --name-only | reveal --stdin --outline` - Analyze changed files
    - `git ls-files "*.ts" | reveal --stdin --format=json` - Export TypeScript structure
    - `find . -name "*.py" | reveal --stdin --format=json | jq '.functions[] | select(.line_count > 100)'` - Complex filtering pipeline

- **Enhanced help text** - Pipeline examples with jq integration
  - Dynamic help: shows jq examples only if jq is installed
  - Clear documentation of stdin workflows
  - Real-world pipeline examples combining find/git/grep with reveal

- **README documentation** - Added "Unix Pipeline Workflows" section
  - Comprehensive stdin examples with find, git, jq
  - CI/CD integration patterns
  - Clear explanation of composability benefits

### Changed
- **Analyzer icons removed** - Completed LLM optimization started in v0.9.0
  - All emoji icons removed from file type registrations
  - Consistent with token optimization strategy (30-40% token savings)
  - Applies to all 18 built-in analyzers

## [0.9.0] - 2025-11-26

### 🌟 Major Feature: Hierarchical Outline Mode

**NEW: `--outline` flag** - See code structure as a beautiful tree!

Transform flat lists into hierarchical views that show relationships at a glance:

```bash
# Before: Flat list
Functions (5):
  app.py:4    create_user(self, username)
  app.py:8    delete_user(self, user_id)
  ...

# After: Hierarchical tree
UserManager (app.py:1)
  ├─ create_user(self, username) [3 lines, depth:0] (line 4)
  ├─ delete_user(self, user_id) [3 lines, depth:0] (line 8)
  └─ UserValidator (nested class, line 12)
     └─ validate_email(self, email) [2 lines, depth:0] (line 15)
```

**Key Benefits:**
- **Instant understanding** - See which methods belong to which classes
- **Nested structure visibility** - Detect nested classes, functions within functions
- **Perfect for AI agents** - Hierarchical context improves code comprehension
- **Combines with other flags** - Use with `--god` for complexity-focused outlines

**Works across languages:**
- Python: Classes with methods, nested classes
- JavaScript/TypeScript: Classes with methods (via TreeSitter)
- Markdown: Heading hierarchy (# → ## → ###)
- Any language with TreeSitter support

### Added
- **`--outline` flag** - Hierarchical tree view of code structure
  - Automatically builds parent-child relationships from line ranges
  - Uses tree characters (├─, └─, │) for visual clarity
  - Shows line numbers for vim/git integration
  - Preserves complexity metrics ([X lines, depth:Y])
  - Example: `reveal app.py --outline`
  - Example: `reveal app.py --outline --god` (outline of only complex code)

- **Enhanced TreeSitter analyzers** - Now track `line_end` for proper hierarchy
  - Classes, structs, and all code elements now have line ranges
  - Enables accurate parent-child relationship detection
  - Fixes: Classes can now contain their methods in outline view

- **God function detection** (`--god` flag) - Find high-complexity code (>50 lines or >4 depth)
  - Quickly identify functions that need refactoring
  - JSON format includes metrics: `line_count`, `depth` for filtering with jq
  - Combines beautifully with `--outline` for focused views
  - Example: `reveal app.py --god` shows only complex functions

- **TreeSitter fallback system** - Automatic support for 35+ additional languages
  - C, C++, C#, Java, PHP, Ruby, Swift, Kotlin, and 27 more languages
  - Graceful fallback when explicit analyzer doesn't exist
  - Transparency: Shows `(fallback: cpp)` indicator in output
  - Metadata included in JSON

- **--no-fallback flag** - Disable automatic fallback for strict workflows

### Changed
- **LLM optimization** - Removed emojis from all output formats (30-40% token savings)
  - Clean, parseable format optimized for AI agents
  - Hierarchical outline adds even more AI-friendly structure

- **Code quality** - Refactored `show_structure()` function (54% complexity reduction)
  - Extracted helper functions: `_format_links()`, `_format_code_blocks()`, `_format_standard_items()`
  - Added `build_hierarchy()` and `render_outline()` for tree rendering
  - Reduced from 208 lines → 95 lines (main function)
  - Improved maintainability with proper type hints

### Improved
- **Help text** - Added clear examples for `--outline` flag
- **Visual clarity** - Tree characters make structure instantly recognizable
- **AI agent workflows** - Hierarchical context improves code understanding
- **Developer experience** - See code organization at a glance

## [0.8.0] - 2025-11-25

### Changed
- **tree-sitter is now a required dependency** (previously optional via `[treesitter]` extra)
  - JavaScript, TypeScript, Rust, Go, and all tree-sitter languages now work out of the box
  - No more silent failures when analyzing JS/TS files without extras installed
  - Simplified installation: just `pip install reveal-cli` (no `[treesitter]` needed)
  - Package size increased from ~50KB to ~15MB (comparable to numpy, black, pytest)

### Improved
- **Better user experience**: Code exploration features work by default
- **Simpler documentation**: One install command instead of two options
- **Cleaner codebase**: Removed optional import logic and conditional checks
- **Aligned with tool identity**: "Semantic code exploration" now works for all languages immediately

### Added
- **Update notifications**: reveal now checks PyPI once per day for newer versions
  - Shows: "⚠️ Update available: reveal 0.8.1 (you have 0.8.0)"
  - Includes install hint: "💡 Update: pip install --upgrade reveal-cli"
  - Non-blocking: 1-second timeout, fails silently on errors
  - Cached: Only checks once per day (~/.config/reveal/last_update_check)
  - Opt-out: Set `REVEAL_NO_UPDATE_CHECK=1` environment variable

### Technical
- Moved `tree-sitter==0.21.3` and `tree-sitter-languages>=1.10.0` from optional to required dependencies
- Simplified `reveal/treesitter.py` by removing `TREE_SITTER_AVAILABLE` conditionals
- Updated README.md to show single installation command
- Kept `[treesitter]` extra as empty for backward compatibility
- Added update checking using urllib (no new dependencies)

### Migration Notes
- **Existing users**: No action required - upgrade works seamlessly
- **New users**: Just `pip install reveal-cli` and everything works
- **Scripts using `[treesitter]`**: Still work (now redundant but harmless)

## [0.7.0] - 2025-11-23

### Added
- **TOML Analyzer** (`.toml`) - Extract sections and top-level keys from TOML configuration files
  - Perfect for exploring `pyproject.toml`, Hugo configs, Cargo.toml
  - Shows `[section]` headers and `[[array]]` sections with line numbers
  - Supports section extraction via `reveal file.toml <section>`
- **Dockerfile Analyzer** (filename: `Dockerfile`) - Extract Docker directives and build stages
  - Shows FROM images, RUN commands, COPY/ADD operations, ENV variables, EXPOSE ports
  - Detects multi-stage builds and displays all directives with line numbers
  - Works with any Dockerfile regardless of case (Dockerfile, dockerfile, DOCKERFILE)
- **Shebang Detection** - Automatically detect file type from shebang for extensionless scripts
  - Python scripts (`#!/usr/bin/env python3`) now work without `.py` extension
  - Bash/Shell scripts (`#!/bin/bash`, `#!/bin/sh`, `#!/bin/zsh`) work without `.sh` extension
  - Enables reveal to analyze TIA's `bin/` directory and other extensionless script collections
  - File extension still takes precedence when present

### Technical Improvements
- Enhanced `get_analyzer()` with fallback chain: extension → filename → shebang
- Case-insensitive filename matching for special files (Dockerfile, Makefile)
- Cross-platform shebang detection with robust error handling
- 32 new comprehensive unit tests (TOML: 7, Dockerfile: 13, Shebang: 12)

### Impact
- File types supported: **16 → 18** (+12.5%)
- TIA ecosystem coverage: ~90% of file types now supported
- Token efficiency: 6-10x improvement for config files and Dockerfiles

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
