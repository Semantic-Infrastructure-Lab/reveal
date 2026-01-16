# Reveal Anti-Patterns: Stop Using grep/find

**Purpose**: Show reveal equivalents for common grep/find/cat patterns

**Token Impact**: Using reveal instead of grep/find/cat = 10-150x token reduction

---

## Quick Reference Table

| Anti-Pattern (❌) | Better Approach (✅) | Token Savings |
|------------------|---------------------|---------------|
| `cat file.py` | `reveal file.py` | ~50-100x |
| `grep -n "function_name" file.py` | `reveal file.py "function_name"` | ~20-50x |
| `find . -name "*.py" -exec grep -l "pattern"` | `reveal 'ast://.?name=*pattern*'` | ~30-60x |
| `grep -r "class Foo" .` | `reveal 'ast://.?name=Foo&type=class'` | ~40-80x |
| `head -50 file.py` | `reveal file.py --head 5` | ~10-20x |

---

## Pattern 1: Reading Files

### ❌ Anti-Pattern: cat entire file
```bash
cat app.py                     # 7,500 tokens for 300-line file
```

### ✅ Reveal Way: Structure first
```bash
reveal app.py                  # 100 tokens - see structure
reveal app.py process_data     # 50 tokens - extract specific function
```

**Why Better**:
- See what's available before reading
- Extract only what you need
- 75x fewer tokens

---

## Pattern 2: Finding Functions

### ❌ Anti-Pattern: grep for function definitions
```bash
grep -n "def process_" file.py
# Shows lines with text, not structure
# No context about function size, complexity
```

### ✅ Reveal Way: AST query
```bash
reveal 'ast://file.py?name=process_*'
# Shows:
# - Function name + line number
# - Lines of code
# - Cyclomatic complexity
# - Full context
```

**Why Better**:
- Structured output (not just text matches)
- Additional metadata (complexity, size)
- Can combine filters: `name=process_*&lines>50`

---

## Pattern 3: Searching Across Multiple Files

### ❌ Anti-Pattern: find + grep pipeline
```bash
find . -name "*.py" -exec grep -l "get_help" {} \;
# Returns file paths only
# No line numbers
# No function context
```

### ✅ Reveal Way: AST query with name filter
```bash
reveal 'ast://.?name=get_help'
# Output:
# reveal/adapters/ast.py:  28  get_help [67 lines, complexity: 6]
# reveal/adapters/help.py:  30  get_help [48 lines, complexity: 7]
# reveal/adapters/python.py: 774  get_help [103 lines, complexity: 10]
```

**Why Better**:
- Shows file:line:name in one step
- Includes size and complexity
- Can further filter: `?name=get_help&lines<50`

---

## Pattern 4: Finding Complex Code

### ❌ Anti-Pattern: Manual inspection
```bash
# 1. List all files
find src/ -name "*.py"

# 2. Read each file
cat src/module1.py
cat src/module2.py
# ... keep reading until you find complex functions
```

### ✅ Reveal Way: Query by complexity
```bash
reveal 'ast://src/?complexity>8'
# Instantly shows only complex functions
```

**Why Better**:
- One command instead of many
- Automatic complexity calculation
- Filter by multiple criteria: `complexity>8&lines>100`

---

## Pattern 5: Extracting Markdown Sections

### ❌ Anti-Pattern: grep + sed/awk
```bash
grep -A 50 "## Integration" README.md
# Shows 50 lines after match
# Hard to know if you got the whole section
```

### ✅ Reveal Way: Extract by section name
```bash
reveal README.md "Integration Patterns"
# Extracts the exact section (detects boundaries automatically)
```

**Why Better**:
- Understands markdown structure
- Extracts complete sections
- No guessing at line counts

---

## Pattern 6: Finding Test Functions

### ❌ Anti-Pattern: grep with regex
```bash
grep -rn "def test_" tests/
# Text matches only
# No metadata
```

### ✅ Reveal Way: Name pattern with wildcards
```bash
reveal 'ast://tests/?name=test_*'
# Structured output with line numbers + complexity
```

**Why Better**:
- Wildcard support: `test_*`, `*helper*`, `setup_?`
- See complexity of test functions
- Find long tests: `name=test_*&lines>50`

---

## Pattern 7: Understanding Project Structure

### ❌ Anti-Pattern: Multiple commands
```bash
ls -la src/
find src/ -name "*.py" | wc -l
grep -r "class " src/ | wc -l
grep -r "def " src/ | wc -l
```

### ✅ Reveal Way: Progressive discovery
```bash
reveal src/                    # Directory structure with file summary
reveal src/main.py             # Specific file structure
reveal src/main.py --outline   # Hierarchical view (classes → methods)
```

**Why Better**:
- Progressive disclosure (general → specific)
- One tool instead of four
- Semantic understanding (not text matching)

---

## Pattern 8: Code Quality Checks

### ❌ Anti-Pattern: Manual pylint/flake8
```bash
pylint file.py                 # Requires separate tool
flake8 file.py                 # Different tool, different output
```

### ✅ Reveal Way: Built-in checks
```bash
reveal file.py --check         # All checks at once
reveal file.py --check --select B,S  # Just bugs & security
```

**Why Better**:
- Integrated with structure exploration
- Consistent output format
- Token-efficient (no tool installation output)

---

## Pattern 9: Finding All References

### ❌ Anti-Pattern: grep -r with false positives
```bash
grep -r "calculate_total" .
# Matches:
# - Function definitions
# - Function calls
# - Comments mentioning it
# - String literals containing the text
```

### ✅ Reveal Way: Semantic search
```bash
# Find definition
reveal 'ast://.?name=calculate_total&type=function'

# Find in specific file
reveal file.py "calculate_total"
```

**Why Better**:
- Semantic understanding (not text matching)
- Fewer false positives
- Structured output with context

---

## Pattern 10: Exploring Unknown Codebase

### ❌ Anti-Pattern: Trial and error
```bash
ls                             # What files are there?
cat app.py                     # Read entire file
grep -n "main" app.py          # Search for entry point
head -100 app.py               # Try reading part of it
```

### ✅ Reveal Way: Progressive exploration
```bash
reveal .                       # What's here?
reveal app.py                  # What's in this file?
reveal app.py main             # Extract specific function
```

**Why Better**:
- Guided discovery (breadcrumbs show next steps)
- Never read more than needed
- 100x token reduction

---

## When to Use grep/find (Rare Cases)

**Use grep when**:
- Searching for exact text strings in logs
- Looking for specific error messages
- Searching non-code files (binaries, data files)

**Use find when**:
- Finding files by modification time
- Complex file permission searches
- Piping to non-reveal tools (xargs, etc.)

**Use cat when**:
- You genuinely need the entire file (rare!)
- Binary file inspection (with `cat -v`)
- Concatenating multiple files

---

## Decision Tree

```
Need to inspect code?
├─ Unknown file? → reveal file.py
├─ Know function name? → reveal file.py "function_name"
├─ Find by pattern? → reveal 'ast://path?name=pattern*'
├─ Find complex code? → reveal 'ast://path?complexity>8'
├─ Check quality? → reveal file.py --check
└─ Read everything? → (Are you sure? Try reveal first!)

Need to search text?
├─ In code (functions/classes)? → reveal 'ast://?name=*pattern*'
├─ In markdown (sections)? → reveal file.md "section name"
├─ Across multiple files? → reveal 'ast://path?name=*pattern*'
└─ Non-code text/logs? → Use grep (OK!)
```

---

## Token Cost Comparison (Real Examples)

| Task | grep/find/cat | reveal | Savings |
|------|--------------|--------|---------|
| Read 300-line Python file | 7,500 tokens | 100 tokens | 75x |
| Find function in file | 7,500 tokens | 50 tokens | 150x |
| Find function across 50 files | 375,000 tokens | 500 tokens | 750x |
| Understand project structure | 10,000 tokens | 200 tokens | 50x |
| Extract markdown section | 2,000 tokens | 100 tokens | 20x |

---

## Pro Tips

1. **Always structure first**: `reveal file.py` before `reveal file.py "function_name"`
2. **Use wildcards**: `name=test_*` instead of exact names
3. **Combine filters**: `name=*handler*&complexity>5&lines<100`
4. **Progressive disclosure**: Directory → File → Function
5. **Read breadcrumbs**: reveal tells you what to do next!
6. **Use --format=json**: For piping to jq or other tools

---

## Common Mistakes

### Mistake 1: Reading files too early
```bash
❌ cat file.py                 # 7,500 tokens
✅ reveal file.py              # 100 tokens, shows structure
✅ reveal file.py "func"       # 50 tokens, extract what you need
```

### Mistake 2: Using grep for structured data
```bash
❌ grep -n "class" *.py        # Text matching
✅ reveal 'ast://.?type=class' # Semantic search
```

### Mistake 3: Not using wildcards
```bash
❌ grep -r "test_login\|test_logout\|test_signup"
✅ reveal 'ast://tests/?name=test_*'
```

### Mistake 4: Ignoring breadcrumbs
```bash
# After running: reveal file.py
# reveal shows: "Next: reveal file.py <function_name>"
# Use that guidance!
```

---

## Getting Help

- `reveal help://` - List all adapters
- `reveal help://ast` - AST query syntax
- `reveal --agent-help` - Quick agent guide
- `reveal help://python-guide` - Comprehensive Python adapter guide
- `reveal --list-supported` - Supported file types

---

## Remember

**The Reveal Principle**: Explore structure before reading content (10-150x token reduction)

**Progressive Discovery**: Directory → File → Element (each step reveals what's possible)

**Breadcrumbs Are Your Friend**: reveal tells you what to do next - listen!

---

## See Also

- [COOL_TRICKS.md](COOL_TRICKS.md) - Correct patterns and best practices
- [AGENT_HELP.md](AGENT_HELP.md) - Task-oriented patterns for AI agents
- [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) - Proper configuration
- [README.md](README.md) - Documentation hub
