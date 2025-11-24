#!/bin/bash
# Cross-Platform Compatibility Checker for Reveal
# Checks for Windows vs Linux encoding and path issues

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ISSUES_FOUND=0

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Cross-Platform Compatibility Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Check for open() without encoding parameter
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 1: File Operations Without Encoding"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Find open() calls without encoding (excluding binary mode and comments)
OPEN_NO_ENCODING=$(grep -rn "open(" --include="*.py" reveal/ 2>/dev/null | \
    grep -v "encoding=" | \
    grep -v "'rb'" | \
    grep -v '"rb"' | \
    grep -v "'wb'" | \
    grep -v '"wb"' | \
    grep -v "^[[:space:]]*#" || true)

if [ -n "$OPEN_NO_ENCODING" ]; then
    echo -e "${RED}❌ FAIL${NC}: Found open() calls without encoding parameter:"
    echo "$OPEN_NO_ENCODING"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
    echo -e "${GREEN}✅ PASS${NC}: All text file operations specify encoding"
fi
echo ""

# 2. Check for hardcoded path separators in production code
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 2: Hardcoded Path Separators (Production Code)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check production code (not tests or validation samples)
HARDCODED_PATHS=$(grep -rn '"/[a-zA-Z]' --include="*.py" reveal/ 2>/dev/null | \
    grep -v "https://" | \
    grep -v "http://" | \
    grep -v "test" || true)

if [ -n "$HARDCODED_PATHS" ]; then
    echo -e "${RED}❌ FAIL${NC}: Found hardcoded Unix paths in production code:"
    echo "$HARDCODED_PATHS"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
    echo -e "${GREEN}✅ PASS${NC}: No hardcoded Unix paths in production code"
fi
echo ""

# 3. Check for os.path usage (should use pathlib)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 3: os.path vs pathlib (Production Code)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for os.path usage in production code
OS_PATH_USAGE=$(grep -rn "os\.path\." --include="*.py" reveal/ 2>/dev/null | \
    grep -v "test" | \
    grep -v "import os.path" || true)

if [ -n "$OS_PATH_USAGE" ]; then
    echo -e "${YELLOW}⚠️  WARNING${NC}: Found os.path usage (prefer pathlib):"
    echo "$OS_PATH_USAGE"
    echo "   (This may be acceptable, but pathlib is preferred for cross-platform)"
else
    echo -e "${GREEN}✅ PASS${NC}: Using pathlib for path operations"
fi
echo ""

# 4. Check for line ending issues (explicit \r\n or \n)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 4: Hardcoded Line Endings"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for explicit line ending handling
LINE_ENDINGS=$(grep -rn '\\r\\n' --include="*.py" reveal/ 2>/dev/null | \
    grep -v "test" | \
    grep -v "comment" || true)

if [ -n "$LINE_ENDINGS" ]; then
    echo -e "${YELLOW}⚠️  WARNING${NC}: Found explicit \\r\\n line endings:"
    echo "$LINE_ENDINGS"
    echo "   (Verify these are intentional and not platform-specific)"
else
    echo -e "${GREEN}✅ PASS${NC}: No hardcoded line endings"
fi
echo ""

# 5. Check Windows console encoding setup
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 5: Windows Console Encoding (main.py)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if main.py has Windows encoding fix
if grep -q "sys.platform == 'win32'" reveal/main.py 2>/dev/null; then
    if grep -q "PYTHONIOENCODING" reveal/main.py 2>/dev/null; then
        echo -e "${GREEN}✅ PASS${NC}: Windows UTF-8 encoding fix present"
    else
        echo -e "${RED}❌ FAIL${NC}: Windows platform check exists but missing encoding fix"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
else
    echo -e "${YELLOW}⚠️  WARNING${NC}: No Windows platform-specific encoding setup"
    echo "   (May cause issues with emoji/unicode on Windows)"
fi
echo ""

# 6. Check for subprocess encoding issues
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 6: Subprocess Encoding"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for subprocess calls without encoding
SUBPROCESS_NO_ENCODING=$(grep -rn "subprocess\." --include="*.py" reveal/ 2>/dev/null | \
    grep -v "encoding=" | \
    grep -v "text=" | \
    grep -v "^[[:space:]]*#" || true)

if [ -n "$SUBPROCESS_NO_ENCODING" ]; then
    echo -e "${YELLOW}⚠️  WARNING${NC}: Found subprocess calls without encoding:"
    echo "$SUBPROCESS_NO_ENCODING"
    echo "   (May need encoding='utf-8' or text=True)"
else
    echo -e "${GREEN}✅ PASS${NC}: No subprocess calls found or all specify encoding"
fi
echo ""

# 7. Check validation samples
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 7: Validation Samples (Cross-Platform Paths)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for hardcoded paths in validation samples
SAMPLE_PATHS=$(grep -rn '"/etc/' validation_samples/ 2>/dev/null || \
    grep -rn '"/usr/' validation_samples/ 2>/dev/null || \
    grep -rn '"/home/' validation_samples/ 2>/dev/null || true)

if [ -n "$SAMPLE_PATHS" ]; then
    echo -e "${RED}❌ FAIL${NC}: Found Unix-specific paths in validation samples:"
    echo "$SAMPLE_PATHS"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
    echo -e "${GREEN}✅ PASS${NC}: Validation samples are cross-platform"
fi
echo ""

# 8. Check for platform-specific imports
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 8: Platform-Specific Imports"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for conditional platform imports
PLATFORM_IMPORTS=$(grep -rn "import.*posix\|import.*nt\|import.*win32" --include="*.py" reveal/ 2>/dev/null || true)

if [ -n "$PLATFORM_IMPORTS" ]; then
    echo -e "${YELLOW}⚠️  INFO${NC}: Found platform-specific imports:"
    echo "$PLATFORM_IMPORTS"
    echo "   (Verify these have cross-platform fallbacks)"
else
    echo -e "${GREEN}✅ PASS${NC}: No platform-specific imports"
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED - CROSS-PLATFORM READY!${NC}"
    echo ""
    echo "No critical cross-platform issues found."
    echo "The codebase appears to be Windows/Linux compatible."
    exit 0
else
    echo -e "${RED}❌ $ISSUES_FOUND CRITICAL ISSUE(S) FOUND${NC}"
    echo ""
    echo "Please fix the issues above before releasing."
    echo "These may cause problems on Windows or Linux."
    exit 1
fi
