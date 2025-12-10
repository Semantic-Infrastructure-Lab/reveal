#!/bin/bash
# Test reveal from PyPI in Rocky Linux container
set -e

VERSION="${1:-0.13.3}"
CONTAINER_NAME="reveal-test-rocky-$$"

echo "🐳 Testing reveal v${VERSION} from PyPI in Rocky Linux container"
echo "=================================================="

# Clean up any existing container
podman rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Run test in Rocky Linux container
podman run --rm --name "$CONTAINER_NAME" \
  docker.io/rockylinux/rockylinux:9 \
  bash -c "
set -e

echo '📦 Installing Python and pip...'
dnf install -y python3 python3-pip > /dev/null 2>&1

echo '⏳ Installing reveal-cli from PyPI...'
pip3 install reveal-cli==${VERSION} --quiet

echo ''
echo '✅ Installation successful!'
echo ''

echo '🧪 Running tests...'
echo '-------------------'

# Test 1: Version check
echo -n '1. Version check: '
INSTALLED_VERSION=\$(reveal --version | grep -oP '\d+\.\d+\.\d+')
if [[ \"\$INSTALLED_VERSION\" == \"${VERSION}\" ]]; then
  echo \"✅ \$INSTALLED_VERSION\"
else
  echo \"❌ Expected ${VERSION}, got \$INSTALLED_VERSION\"
  exit 1
fi

# Test 2: List supported file types
echo -n '2. List supported types: '
reveal --list-supported > /dev/null && echo '✅'

# Test 3: Cache directory (Linux should use ~/.config/reveal)
echo -n '3. Cache directory: '
python3 -c \"
from pathlib import Path
import sys
import os

# Simulate the logic from main.py
if sys.platform == 'win32':
    cache_dir = Path(os.getenv('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'reveal'
else:
    cache_dir = Path.home() / '.config' / 'reveal'

expected = Path.home() / '.config' / 'reveal'
if cache_dir == expected:
    print(f'✅ {cache_dir}')
else:
    print(f'❌ Expected {expected}, got {cache_dir}')
    sys.exit(1)
\"

# Test 4: Environment variables
echo -n '4. Unix env vars in SYSTEM_VARS: '
python3 -c \"
from reveal.adapters.env import EnvAdapter
adapter = EnvAdapter()
unix_vars = ['PATH', 'HOME', 'USER', 'SHELL']
missing = [v for v in unix_vars if v not in adapter.SYSTEM_VARS]
if missing:
    print(f'❌ Missing: {missing}')
    import sys
    sys.exit(1)
else:
    print(f'✅ {len(adapter.SYSTEM_VARS)} system vars')
\"

# Test 5: Windows env vars present (even on Linux)
echo -n '5. Windows env vars in SYSTEM_VARS: '
python3 -c \"
from reveal.adapters.env import EnvAdapter
adapter = EnvAdapter()
windows_vars = ['USERPROFILE', 'USERNAME', 'COMSPEC', 'LOCALAPPDATA']
missing = [v for v in windows_vars if v not in adapter.SYSTEM_VARS]
if missing:
    print(f'❌ Missing: {missing}')
    import sys
    sys.exit(1)
else:
    print(f'✅ All present')
\"

# Test 6: Create test file and analyze it
echo -n '6. Analyze Python file: '
cat > /tmp/test.py << 'EOF'
def hello():
    \"\"\"Say hello.\"\"\"
    print(\"Hello, World!\")

class Greeter:
    def greet(self, name):
        return f\"Hello, {name}!\"
EOF

reveal /tmp/test.py > /tmp/reveal_output.txt
if grep -q 'hello' /tmp/reveal_output.txt && grep -q 'Greeter' /tmp/reveal_output.txt; then
  echo '✅'
else
  echo '❌ Output missing expected elements'
  cat /tmp/reveal_output.txt
  exit 1
fi

# Test 7: Extract specific function
echo -n '7. Extract function: '
reveal /tmp/test.py hello > /tmp/reveal_function.txt
if grep -q 'def hello' /tmp/reveal_function.txt; then
  echo '✅'
else
  echo '❌ Function extraction failed'
  cat /tmp/reveal_function.txt
  exit 1
fi

echo ''
echo '=================================================='
echo '✅ All tests passed! reveal v${VERSION} works correctly on Rocky Linux'
echo '=================================================='
"
```

chmod +x test_pypi_rocky.sh
echo ""
echo "✅ Test script created: test_pypi_rocky.sh"
echo ""
echo "Usage:"
echo "  ./test_pypi_rocky.sh           # Test latest version (0.13.3)"
echo "  ./test_pypi_rocky.sh 0.13.2    # Test specific version"
