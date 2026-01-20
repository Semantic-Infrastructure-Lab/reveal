# Analyzer Development Patterns

**Date:** 2026-01-03
**Purpose:** Codify best practices for analyzer development to ensure consistent, performant, maintainable code

---

## Quick Reference

### ✅ Use AST When:
- Parsing structured languages (Python, JS, Markdown, HTML, etc.)
- Extracting nested structures (imports, functions, classes)
- Context matters (code vs. comments vs. strings)
- Parser library exists and is mature

### ✅ Use Regex When:
- Validating formats (dates, emails, URLs)
- Parsing template syntax (not valid in target language)
- No AST parser available (e.g., nginx config)
- Simple text patterns (single-line directives)

### ⚠️ NEVER:
- Extract AST node text then regex it (use child nodes!)
- Compile patterns inline in loops
- Define compiled patterns but not use them
- Duplicate parsing logic across analyzers/rules

---

## Pattern 1: Compiled Regex at Class Level

### ✅ Good Example (GDScript)

```python
class GDScriptAnalyzer(FileAnalyzer):
    """GDScript file analyzer."""

    # Compile regex patterns ONCE at class level
    CLASS_PATTERN = re.compile(r'^\s*class\s+(\w+)\s*:')
    FUNC_PATTERN = re.compile(r'^\s*func\s+(\w+)\s*\((.*?)\)')
    SIGNAL_PATTERN = re.compile(r'^\s*signal\s+(\w+)(?:\((.*?)\))?')

    def _parse_class_line(self, line: str, line_num: int):
        """Parse a class definition line."""
        if match := self.CLASS_PATTERN.match(line):  # Use compiled pattern
            return {'line': line_num, 'name': match.group(1)}
        return None
```

**Why:**
- Pattern compiled once when class loads
- Reused across all instances and calls
- **999x faster** for large files vs. inline compilation

### ❌ Bad Example

```python
class MyAnalyzer(FileAnalyzer):
    # Pattern defined but...
    CLASS_PATTERN = re.compile(r'^\s*class\s+(\w+)\s*:')

    def parse(self, line):
        # ...NOT USED! Compiling inline instead
        match = re.match(r'^\s*class\s+(\w+)\s*:', line)  # WRONG!
```

**Impact:** Negates performance optimization, wastes memory

---

## Pattern 2: AST-First Architecture

### ✅ Good Example (Markdown)

```python
class MarkdownAnalyzer(TreeSitterAnalyzer):
    """Markdown analyzer using tree-sitter."""

    language = 'markdown'

    def _extract_headings(self) -> List[Dict]:
        """Extract headings using AST."""
        if not self.tree:
            return self._extract_headings_regex()  # Fallback

        # Use AST nodes
        heading_nodes = self._find_nodes_by_type('atx_heading')
        return [self._parse_heading_node(node) for node in heading_nodes]

    def _extract_headings_regex(self) -> List[Dict]:
        """Fallback regex extraction."""
        # Only used if tree-sitter fails
        ...
```

**Architecture:**
1. **Primary:** AST-based extraction
2. **Fallback:** Regex extraction if AST unavailable
3. **Comment:** Explain why fallback exists

**Benefits:**
- Robust (handles edge cases)
- Correct (respects structure, e.g., # in code blocks)
- Maintainable (AST changes reflected automatically)

### ❌ Bad Example

```python
def _extract_links(self):
    """Extract links using regex."""
    # Has tree-sitter available but doesn't use it!
    link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
    for match in re.finditer(link_pattern, self.content):
        ...
```

**Problems:**
- Misses links in complex structures
- Can't handle nested brackets `[text [nested]](url)`
- Breaks on escaped characters `\[not a link\]`

---

## Pattern 3: Avoid AST Text + Regex

### ❌ Bad Example (Common Anti-Pattern)

```python
# Get text from AST node
import_text = analyzer._get_node_text(node)

# Then regex it!
match = re.match(r'from\s+(\.*)(\S*)\s+import\s+(.+)', import_text)
dots = len(match.group(1))
module = match.group(2)
```

**Problems:**
- Already have AST structure
- Re-parsing text we just extracted
- Regex can fail on edge cases

### ✅ Good Example (Navigate AST)

```python
# Navigate child nodes directly
dots_node = node.child_by_field_name('relative_import')
dots = len(dots_node.text) if dots_node else 0

module_node = node.child_by_field_name('module_name')
module = self._get_node_text(module_node) if module_node else ''
```

**Benefits:**
- Use typed AST nodes
- Handles all edge cases tree-sitter handles
- More semantic, less brittle

---

## Pattern 4: Use Standard Library Over Regex

### ✅ Good Example (URL Parsing)

```python
from urllib.parse import urlparse

def _classify_link(self, url: str):
    """Extract URL components."""
    parsed = urlparse(url)
    return {
        'protocol': parsed.scheme,  # 'https'
        'domain': parsed.netloc,    # 'example.com:8080'
        'path': parsed.path,        # '/foo/bar'
    }
```

**Why:**
- Handles ports, IPv6, authentication
- Robust against edge cases
- Standard library = well-tested

### ❌ Bad Example

```python
def _classify_link(self, url: str):
    """Extract domain using regex."""
    domain_match = re.match(r'https?://([^/]+)', url)
    domain = domain_match.group(1) if domain_match else None
```

**Problems:**
- Doesn't handle `https://user:pass@example.com:8080/path`
- Doesn't handle IPv6 `https://[::1]/path`
- Reinvents the wheel

---

## Pattern 5: Simple String Methods Over Regex

### ✅ Good Example

```python
# Strip parentheses from import names
names_part = names_part.strip('()')

# Remove prefix
use_path = use_text.removeprefix('use ')

# Check if starts with
if url.startswith(('http://', 'https://')):
    ...
```

**Why:**
- Clearer intent
- Faster execution
- No regex compilation overhead

### ❌ Bad Example

```python
# Regex overkill
names_part = re.sub(r'[()]', '', names_part)  # Just strip!

# Regex for simple prefix
use_text = re.sub(r'^\s*use\s+', '', use_text)  # removeprefix + strip!

# Regex for simple check
if re.match(r'https?://', url):  # Just startswith!
    ...
```

---

## Pattern 6: Parser-Specific Tools

### ✅ Good Examples by Language

**HTML:**
```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(content, 'lxml')
links = soup.find_all('a', href=True)  # DOM navigation
```

**YAML/JSON:**
```python
import yaml
import json

data = yaml.safe_load(content)  # Parsed structure
value = data['key']['nested']   # Navigate structure
```

**TOML:**
```python
import tomllib  # Python 3.11+

data = tomllib.loads(content)
```

**Markdown:**
```python
class MarkdownAnalyzer(TreeSitterAnalyzer):
    language = 'markdown'

    def get_structure(self):
        heading_nodes = self._find_nodes_by_type('atx_heading')
        link_nodes = self._find_nodes_by_type('link')
```

### ⚠️ When Parsers Don't Exist

**Config Files (nginx, apache):**
- Regex is acceptable
- Or use specialized library if available
- Document why regex is chosen

**Template Syntax:**
- Regex for template directives
- Parser for base language

```python
# Good: BeautifulSoup for HTML, regex for templates
soup = BeautifulSoup(content, 'lxml')  # HTML structure
jinja_vars = re.findall(r'\{\{\s*(\w+)\s*\}\}', content)  # Template vars
```

---

## Pattern 7: Rules Use Analyzer Structure

### ✅ Good Example (Post Phase 2 Refactoring)

```python
class L001(BaseRule):
    """Detect broken internal links."""

    def check(self, file_path, structure, content):
        """Validate links from analyzer structure."""
        # Get links from structure (analyzer already parsed them)
        if structure and 'links' in structure:
            links = structure['links']
        else:
            # Fallback: extract links if not in structure
            from ...base import get_analyzer
            analyzer_class = get_analyzer(file_path)
            if analyzer_class:
                analyzer = analyzer_class(file_path)
                links = analyzer._extract_links()
            else:
                return []

        # Validate each link (no re-parsing!)
        for link in links:
            url = link.get('url', '')
            line_num = link.get('line', 1)
            text = link.get('text', '')

            if link.get('type') == 'internal' and self._is_broken(url):
                yield Detection(
                    line=line_num,
                    context=f"[{text}]({url})",
                    ...
                )
```

**Architecture:**
- **Primary:** Use `structure['links']` if available
- **Fallback:** Create analyzer and extract links if not
- **Benefits:**
  - Single source of truth (analyzer)
  - No duplicate parsing patterns
  - Rules are validators, not parsers

**Implementation Notes:**
- File checker calls `analyzer.get_structure()` (defaults: only headings for markdown)
- Rules request missing features via fallback
- Future optimization: File checker could request `extract_links=True` for markdown

### ❌ Bad Example (Pre Phase 2)

```python
class L001(BaseRule):
    """Detect broken links."""

    # ❌ Duplicate parsing pattern from analyzer
    LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^\)]+)\)')

    def check(self, file_path, structure, content):
        """Re-parse content instead of using structure."""
        # ❌ Ignores 'structure' parameter entirely!
        # ❌ Re-parses 'content' with regex
        for match in self.LINK_PATTERN.finditer(content):
            text = match.group(1)
            url = match.group(2)
            ...
```

**Problems:**
- ❌ **Duplication:** Same regex in analyzer AND rule
- ❌ **Performance:** Parse content twice (analyzer + rule)
- ❌ **Inconsistency:** Analyzer improves to AST, rule doesn't benefit
- ❌ **Maintenance:** Bug fixes need two locations

**Phase 2 Refactoring (2026-01-03):**
- ✅ L001, L002, L003 now use `structure['links']`
- ✅ Removed duplicate LINK_PATTERN definitions
- ✅ Removed duplicate HEADING_PATTERN from L001
- ✅ Rules use analyzer's `_extract_headings()` method
- ✅ All 1320 tests passing, no regressions

---

## Pattern 8: Migrate Regex to AST Where Parsers Exist

### ✅ Good Example (Post Phase 3 AST Migration)

```python
class MarkdownAnalyzer(TreeSitterAnalyzer):
    """Markdown analyzer using tree-sitter AST."""

    language = 'markdown'

    def _extract_links(self, link_type=None, domain=None):
        """Extract links using tree-sitter AST."""
        if not self.tree:
            return self._extract_links_regex(link_type, domain)  # Fallback

        links = []

        # Find all 'link' nodes in AST
        link_nodes = self._find_nodes_by_type('link')

        for node in link_nodes:
            text = None
            url = None

            # Navigate AST children
            for child in node.children:
                if child.type == 'link_text':
                    for text_node in child.children:
                        if text_node.type == 'text':
                            text = text_node.text.decode('utf-8')
                            break
                elif child.type == 'link_destination':
                    for text_node in child.children:
                        if text_node.type == 'text':
                            url = text_node.text.decode('utf-8')
                            break

            if text and url:
                # ✅ Column position tracking from AST
                line = node.start_point[0] + 1
                column = node.start_point[1] + 1

                link_info = self._classify_link(url, text, line)
                link_info['column'] = column  # AST provides precise position
                links.append(link_info)

        return links
```

**Benefits:**
- ✅ **Column position tracking:** AST provides exact position (line + column)
- ✅ **Edge case handling:** Ignores links in code blocks automatically
- ✅ **Correctness:** Handles escaped brackets, nested syntax
- ✅ **Maintainability:** AST parser maintained by tree-sitter community
- ✅ **Future-proof:** Parser improvements benefit code automatically

### ❌ Bad Example (Pre Phase 3 Regex)

```python
def _extract_links(self, link_type=None, domain=None):
    """Extract links using regex."""
    links = []

    # ❌ Regex can't handle edge cases correctly
    link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'

    for i, line in enumerate(self.lines, 1):
        for match in re.finditer(link_pattern, line):
            text = match.group(1)
            url = match.group(2)
            # ❌ No column tracking
            # ❌ Matches links inside code blocks (wrong!)
            # ❌ Breaks on nested brackets: [text [nested]](url)
            # ❌ Breaks on escaped brackets: [text \]](url)
            links.append({
                'line': i,
                'text': text,
                'url': url,
                # ❌ No column position
            })

    return links
```

**Problems:**
- ❌ **No column tracking:** Can't point to exact position
- ❌ **Code fence bug:** Extracts links from code blocks
- ❌ **Edge cases:** Fails on nested/escaped brackets
- ❌ **Maintenance:** Regex becomes complex for edge cases

### Phase 3 Migration Results (2026-01-03)

**Links Migration:**
- ✅ Migrated `_extract_links()` to use tree-sitter 'link' nodes
- ✅ Added `_extract_links_regex()` fallback
- ✅ Column position tracking (node.start_point[1])
- ✅ Correctly ignores links in code blocks
- ✅ Handles all link types (internal, external, email)

**Code Blocks Migration:**
- ✅ Migrated `_extract_code_blocks()` to use 'fenced_code_block' nodes
- ✅ Migrated `_extract_inline_code_ast()` to use 'code_span' nodes
- ✅ Added `_extract_code_blocks_state_machine()` fallback
- ✅ Preserves language filtering and inline code extraction
- ✅ Column position tracking for inline code

**Test Results:**
- ✅ All 1517 tests passing (no regressions)
- ✅ AST-based extraction 100% compatible with existing API
- ✅ Fallback mechanisms maintain reliability

**Edge Cases Handled:**
- ✅ Links inside code blocks (ignored by AST)
- ✅ Nested syntax in links (AST handles correctly)
- ✅ Multiple code blocks with different languages
- ✅ Inline code within paragraphs

---

## Decision Matrix

### Should I use AST or Regex?

```
┌─────────────────────────────────┬──────────┬─────────┐
│ Use Case                        │ AST      │ Regex   │
├─────────────────────────────────┼──────────┼─────────┤
│ Parse Python/JS/Rust/Go imports │ ✅ Yes   │ ❌ No   │
│ Parse Markdown structure        │ ✅ Yes   │ ❌ No   │
│ Parse HTML                      │ ✅ Yes   │ ❌ No   │
│ Parse JSON/YAML/TOML            │ ✅ stdlib│ ❌ No   │
│ Extract template vars {{x}}     │ ❌ No    │ ✅ Yes  │
│ Parse nginx config              │ ⚠️ Maybe │ ✅ Yes  │
│ Validate date format YYYY-MM-DD │ ❌ No    │ ✅ Yes  │
│ Validate email format           │ ❌ No    │ ✅ Yes  │
│ Extract URL domain              │ ✅ urllib│ ❌ No   │
│ Strip parentheses from string   │ ✅ strip │ ❌ No   │
│ Check if string starts with X   │ ✅ starts│ ❌ No   │
└─────────────────────────────────┴──────────┴─────────┘
```

### When to choose?

**Choose AST if:**
- ✅ Parser library exists (tree-sitter, BeautifulSoup, stdlib)
- ✅ Structure is complex (nesting, context-sensitivity)
- ✅ Edge cases matter (escapes, quotes, comments)

**Choose Regex if:**
- ✅ No parser available
- ✅ Simple pattern matching (validation)
- ✅ Template syntax (not valid in base language)
- ✅ Single-line directives in config files

**Choose stdlib if:**
- ✅ Standard library has it (urlparse, json, yaml, toml)
- ✅ String methods work (strip, split, startswith, etc.)

---

## Performance Guidelines

### Pattern Compilation

```python
# ❌ NEVER compile in loops
for line in lines:
    match = re.match(r'pattern', line)  # Compiles every iteration!

# ✅ Compile at class level
class MyAnalyzer:
    PATTERN = re.compile(r'pattern')

    def parse(self, lines):
        for line in lines:
            match = self.PATTERN.match(line)  # Reuses compiled pattern
```

**Impact:** For 1000 lines:
- Inline: 1000 compilations
- Class-level: 1 compilation
- **999x faster!**

### Iteration Efficiency

```python
# ❌ Multiple passes over same data
counts = {
    'type_a': len([x for x in items if x.type == 'a']),
    'type_b': len([x for x in items if x.type == 'b']),
    'type_c': len([x for x in items if x.type == 'c']),
}  # O(3n) = 3 iterations

# ✅ Single pass with Counter
from collections import Counter

type_counts = Counter(x.type for x in items)  # O(n) = 1 iteration
counts = {
    'type_a': type_counts['a'],
    'type_b': type_counts['b'],
    'type_c': type_counts['c'],
}
```

**Impact:** For 100 items, 3 types:
- Multiple passes: 300 iterations
- Single pass: 100 iterations
- **3x faster** (scales with number of types)

---

## Common Anti-Patterns

### 1. The "Regex Everything" Anti-Pattern

```python
# ❌ Using regex when AST is available
class PythonAnalyzer:
    def extract_imports(self, content):
        # tree-sitter is available but not used!
        pattern = r'from\s+(\S+)\s+import\s+(.+)'
        return re.findall(pattern, content)
```

**Fix:** Use tree-sitter for Python parsing

### 2. The "Inconsistent Compilation" Anti-Pattern

```python
# ❌ Define but don't use compiled patterns
class MyAnalyzer:
    PATTERN = re.compile(r'foo')  # Defined

    def parse(self, text):
        return re.match(r'foo', text)  # Not used!
```

**Fix:** Use `self.PATTERN.match(text)`

### 3. The "AST Then Regex" Anti-Pattern

```python
# ❌ Extract AST text, then regex it
node_text = analyzer._get_node_text(node)
match = re.search(r'pattern', node_text)
```

**Fix:** Navigate AST child nodes directly

### 4. The "Duplication Across Layers" Anti-Pattern

```python
# ❌ Analyzer and Rule both parse
class MarkdownAnalyzer:
    LINK_PATTERN = re.compile(r'\[...\]\(...\)')

class L001(BaseRule):
    LINK_PATTERN = re.compile(r'\[...\]\(...\)')  # Duplicate!
```

**Fix:** Rule uses `structure['links']` from analyzer

### 5. The "Regex Overkill" Anti-Pattern

```python
# ❌ Regex for simple operations
text = re.sub(r'[()]', '', text)        # Use text.strip('()')
text = re.sub(r'^\s*use\s+', '', text)  # Use text.removeprefix('use').strip()
if re.match(r'https?://', url):         # Use url.startswith(('http://', 'https://'))
```

**Fix:** Use string methods

---

## Checklist for New Analyzers

### Before Writing Code

- [ ] Does a parser exist for this language? (tree-sitter, BeautifulSoup, stdlib)
- [ ] If yes, plan to use it as primary method
- [ ] If no, document why regex is chosen
- [ ] Identify all patterns that will be needed
- [ ] Plan to compile patterns at class level

### While Writing Code

- [ ] All regex patterns compiled at class level
- [ ] All compiled patterns actually used (not re-compiling inline)
- [ ] Use AST navigation, not AST text extraction + regex
- [ ] Use stdlib when applicable (urlparse, string methods)
- [ ] Avoid multiple iterations over same data
- [ ] Document any regex fallbacks for AST

### After Writing Code

- [ ] Run tests (all passing)
- [ ] Review: Any AST text + regex patterns?
- [ ] Review: Any inline pattern compilation?
- [ ] Review: Any regex that could be string methods?
- [ ] Review: Any regex that could be stdlib?
- [ ] Update this document if new patterns emerge

---

## Migration Guide

### Migrating Regex to AST

**Step 1:** Verify parser exists
```python
# Check if tree-sitter grammar available
from reveal.base import get_analyzer
analyzer = get_analyzer('file.md')
print(analyzer.language)  # Should show language name
```

**Step 2:** Find node types
```python
# Explore AST structure
def _debug_ast(node, indent=0):
    print('  ' * indent + node.type)
    for child in node.children:
        _debug_ast(child, indent + 1)

_debug_ast(analyzer.tree.root_node)
```

**Step 3:** Replace regex with AST navigation
```python
# Before
links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', content)

# After
link_nodes = analyzer._find_nodes_by_type('link')
links = [self._parse_link_node(node) for node in link_nodes]
```

**Step 4:** Keep regex fallback
```python
def extract_links(self):
    if self.tree:
        return self._extract_links_ast()
    return self._extract_links_regex()  # Fallback
```

---

## Examples from Reveal

### Excellent: HTML Analyzer

```python
from bs4 import BeautifulSoup

class HTMLAnalyzer(FileAnalyzer):
    """HTML analyzer - exemplary pattern."""

    def __init__(self, path):
        # Use DOM parser for HTML
        self.soup = BeautifulSoup(self.content, 'lxml')

    def _extract_links(self):
        # BeautifulSoup for HTML structure
        return [{'url': a['href']} for a in self.soup.find_all('a', href=True)]

    def _detect_template_type(self):
        # Regex ONLY for template syntax (not valid HTML)
        if re.search(r'\{\{.*?\}\}', self.content):
            return 'jinja2'
        return None
```

**Why Excellent:**
- Right tool for each job (BeautifulSoup for HTML, regex for templates)
- Clear separation
- No mixing

### Good: Python Imports

```python
class PythonExtractor(LanguageExtractor):
    """Python import extractor - good AST usage."""

    def extract_imports(self, file_path):
        analyzer = get_analyzer(str(file_path))
        import_nodes = analyzer._find_nodes_by_type('import_statement')
        return [self._parse_node(node) for node in import_nodes]
```

**Why Good:**
- Uses tree-sitter
- No regex on structured code

**Could Improve:**
- Some AST text + regex (should navigate child nodes)

### Needs Work: Markdown Links

```python
# Current
link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
links = re.finditer(link_pattern, content)

# Should be
link_nodes = self._find_nodes_by_type('link')
links = [self._parse_link_node(node) for node in link_nodes]
```

---

## Version History

### 2026-01-03: Initial Version
- Created after regex/AST audit (aerial-sphinx-0103)
- Phase 1 improvements committed
- Patterns codified from audit findings

---

## Related Documents

- `REGEX_AST_AUDIT.md` - Full audit results and recommendations
- `AGENT_HELP.md` - General Reveal anti-patterns
- `README.md` - Reveal overview

---

**Remember:** When in doubt:
1. Check if parser exists
2. Prefer AST over regex
3. Prefer stdlib over regex
4. Compile patterns at class level
5. Don't duplicate parsing logic

## See Also

- [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) - Create custom adapters
- [PYTHON_ADAPTER_GUIDE.md](PYTHON_ADAPTER_GUIDE.md) - Python analysis examples
- [DUPLICATE_DETECTION_GUIDE.md](DUPLICATE_DETECTION_GUIDE.md) - Duplicate detection patterns
- [README.md](README.md) - Documentation hub
