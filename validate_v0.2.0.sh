#!/bin/bash
# Validation script for reveal v0.2.0
# Run this in next session before publishing to PyPI

set -e  # Exit on any error

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  REVEAL v0.2.0 VALIDATION SUITE                            ║"
echo "║  Run this before merging to master and publishing to PyPI  ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0

# Test counter
test_count=0

run_test() {
    test_count=$((test_count + 1))
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "TEST $test_count: $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    FAILED=$((FAILED + 1))
}

warn() {
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

# ============================================================================
# PHASE 1: Installation & Setup
# ============================================================================

run_test "Installation Check"
echo "Checking if reveal is installed..."
if python3 -c "import reveal; print(reveal.__version__)" 2>/dev/null; then
    VERSION=$(python3 -c "import reveal; print(reveal.__version__)")
    if [ "$VERSION" = "0.2.0" ]; then
        pass "Version is 0.2.0"
    else
        fail "Version is $VERSION, expected 0.2.0"
    fi
else
    warn "Not installed - installing in editable mode..."
    pip install -e .[treesitter] > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        pass "Installation successful"
    else
        fail "Installation failed"
        exit 1
    fi
fi

# ============================================================================
# PHASE 2: Core Functionality Tests
# ============================================================================

run_test "CLI Help"
if python3 -m reveal.main --help > /dev/null 2>&1; then
    pass "Help command works"
else
    fail "Help command failed"
fi

run_test "Directory Tree View"
if python3 -m reveal.main reveal/ --depth 1 > /tmp/reveal_test_dir.txt 2>&1; then
    if grep -q "📁 reveal/" /tmp/reveal_test_dir.txt; then
        pass "Directory tree displays correctly"
    else
        fail "Directory tree output incorrect"
    fi
else
    fail "Directory tree command failed"
fi

run_test "Python File Structure"
if python3 -m reveal.main reveal/base.py > /tmp/reveal_test_struct.txt 2>&1; then
    if grep -q "FileAnalyzer" /tmp/reveal_test_struct.txt; then
        pass "Python structure extraction works"
    else
        fail "Python structure extraction missing expected content"
    fi
else
    fail "Python structure extraction failed"
fi

run_test "Function Signature Display (Bug Fix Validation)"
python3 -m reveal.main reveal/base.py > /tmp/reveal_test_sig.txt 2>&1
if grep -q "(__init__)" /tmp/reveal_test_sig.txt || grep -q "(self, path: str)" /tmp/reveal_test_sig.txt; then
    if ! grep -q "def __init__" /tmp/reveal_test_sig.txt; then
        pass "Function signatures display correctly (no 'def' prefix bug)"
    else
        fail "Function signature bug still present (showing 'def' in signature)"
    fi
else
    warn "Could not validate signature format"
fi

run_test "Element Extraction"
if python3 -m reveal.main reveal/base.py FileAnalyzer > /tmp/reveal_test_elem.txt 2>&1; then
    if grep -q "class FileAnalyzer" /tmp/reveal_test_elem.txt; then
        pass "Element extraction works"
    else
        fail "Element extraction missing expected content"
    fi
else
    fail "Element extraction failed"
fi

# ============================================================================
# PHASE 3: Multi-Language Support
# ============================================================================

run_test "Markdown File Support"
if python3 -m reveal.main README.md > /tmp/reveal_test_md.txt 2>&1; then
    if grep -q "Headings" /tmp/reveal_test_md.txt; then
        pass "Markdown analyzer works"
    else
        fail "Markdown analyzer not working"
    fi
else
    fail "Markdown file failed"
fi

run_test "JSON/YAML Analyzer Registration"
python3 -c "from reveal.analyzers.yaml_json import YamlAnalyzer, JsonAnalyzer; print('OK')" 2>&1
if [ $? -eq 0 ]; then
    pass "YAML/JSON analyzers import correctly"
else
    fail "YAML/JSON analyzers import failed"
fi

# ============================================================================
# PHASE 4: Edge Cases & Error Handling
# ============================================================================

run_test "Non-existent File Error Handling"
if python3 -m reveal.main /tmp/nonexistent_file_12345.py > /tmp/reveal_test_err1.txt 2>&1; then
    fail "Should have failed for non-existent file"
else
    if grep -q "not found" /tmp/reveal_test_err1.txt; then
        pass "Non-existent file handled gracefully"
    else
        warn "Error message could be clearer"
    fi
fi

run_test "Unsupported File Type"
touch /tmp/test_reveal.xyz
if python3 -m reveal.main /tmp/test_reveal.xyz > /tmp/reveal_test_err2.txt 2>&1; then
    warn "Unsupported file didn't error (may have fallback)"
else
    if grep -q "No analyzer" /tmp/reveal_test_err2.txt; then
        pass "Unsupported file type handled gracefully"
    else
        warn "Error message could be clearer"
    fi
fi
rm -f /tmp/test_reveal.xyz

# ============================================================================
# PHASE 5: Code Quality Checks
# ============================================================================

run_test "No Engineering Debt Naming"
DEBT_FOUND=0
if find reveal/ -name "*_new.*" -o -name "*_old.*" -o -name "*_temp.*" -o -name "*_v2.*" 2>/dev/null | grep -v _archive; then
    fail "Found engineering debt naming patterns"
    DEBT_FOUND=1
fi
if [ $DEBT_FOUND -eq 0 ]; then
    pass "No engineering debt naming patterns found"
fi

run_test "Import Path Validation"
if grep -r "analyzers_new\|new_cli" reveal/ --include="*.py" 2>/dev/null | grep -v _archive | grep -v ".pyc"; then
    fail "Found references to old 'new_' naming in imports"
else
    pass "All imports use canonical paths"
fi

run_test "Version Consistency"
INIT_VERSION=$(grep "__version__" reveal/__init__.py | cut -d'"' -f2)
TOML_VERSION=$(grep "^version" pyproject.toml | cut -d'"' -f2)
if [ "$INIT_VERSION" = "$TOML_VERSION" ]; then
    if [ "$INIT_VERSION" = "0.2.0" ]; then
        pass "Version consistent across files (0.2.0)"
    else
        fail "Version consistent but not 0.2.0: $INIT_VERSION"
    fi
else
    fail "Version mismatch: __init__.py=$INIT_VERSION, pyproject.toml=$TOML_VERSION"
fi

# ============================================================================
# PHASE 6: TreeSitter Support (Optional)
# ============================================================================

run_test "TreeSitter Installation (Optional)"
if python3 -c "import tree_sitter_languages" 2>/dev/null; then
    pass "TreeSitter available for multi-language support"
    
    # Test with a language that needs TreeSitter
    run_test "Rust File Support (TreeSitter)"
    cat > /tmp/test.rs << 'EOF'
fn main() {
    println!("Hello");
}

fn calculate(x: i32) -> i32 {
    x * 2
}
EOF
    if python3 -m reveal.main /tmp/test.rs > /tmp/reveal_test_rust.txt 2>&1; then
        if grep -q "main" /tmp/reveal_test_rust.txt; then
            pass "Rust analyzer works via TreeSitter"
        else
            warn "Rust file processed but structure unclear"
        fi
    else
        fail "Rust file processing failed"
    fi
    rm -f /tmp/test.rs
else
    warn "TreeSitter not installed (optional, but recommended)"
    echo "    Install with: pip install tree-sitter==0.21.3 tree-sitter-languages>=1.10.0"
fi

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  VALIDATION SUMMARY                                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo -e "${GREEN}Passed: $PASSED${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Failed: $FAILED${NC}"
else
    echo -e "Failed: $FAILED"
fi
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ ALL TESTS PASSED - READY FOR RELEASE!                  ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. git checkout master"
    echo "  2. git merge clean-redesign"
    echo "  3. git tag v0.2.0"
    echo "  4. git push origin master --tags"
    echo "  5. python3 -m build"
    echo "  6. python3 -m twine upload dist/*"
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ❌ TESTS FAILED - DO NOT RELEASE YET                      ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Fix the failures above before releasing."
    exit 1
fi
