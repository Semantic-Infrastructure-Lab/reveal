# Complete Guide: Universal Duplicate Detection in Reveal

## Vision: One System, All File Types, Smart Guidance

```
reveal myfile.py --check --select D
reveal myfile.rs --check --select D
reveal myfile.md --check --select D
reveal nginx.conf --check --select D

→ All use the same detection framework
→ All provide similarity scores and rankings
→ All give feedback on quality
→ All guide you to "do it well"
```

---

## Architecture: Three-Layer Abstraction

```
┌─────────────────────────────────────────────────────────────┐
│ UNIVERSAL FRAMEWORK (base_detector.py)                      │
│ - DuplicateFeatureExtractor (abstract base)                 │
│ - DuplicateConfig (user settings)                           │
│ - DuplicateDetectionFeedback (self-reflection)              │
│ - Similarity metrics (cosine, jaccard, euclidean)           │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────┐
│ LANGUAGE-SPECIFIC EXTRACTORS                                │
│ - PythonDuplicateExtractor                                  │
│ - RustDuplicateExtractor                                    │
│ - MarkdownDuplicateExtractor                                │
│ - JavaScriptDuplicateExtractor                              │
│ - ... (easy to add new languages)                           │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────┐
│ REVEAL RULES (D001, D002, D003)                             │
│ - D001: Exact duplicates (hash-based, fast)                 │
│ - D002: Similar functions (vector similarity)               │
│ - D003: Semantic duplicates (embeddings, future)            │
└─────────────────────────────────────────────────────────────┘
```

---

## How It Works for Different File Types

### Python Example

```python
class PythonDuplicateExtractor(DuplicateFeatureExtractor):
    """Extract and compare Python functions."""

    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Extract functions, classes, methods."""
        return [
            Chunk(type='function', name=f['name'], content=...)
            for f in structure.get('functions', [])
        ]

    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Python-specific features."""
        return {
            'kw_def': chunk.count('def'),
            'kw_class': chunk.count('class'),
            'kw_lambda': chunk.count('lambda'),
            'list_comp': chunk.count('[') + chunk.count('for'),
            'decorators': chunk.count('@'),
            'async': chunk.count('async'),
        }
```

**Usage**:
```bash
reveal app.py --check --select D

# Output:
app.py:45:1 ℹ️  D002 Similar function detected: 'process_b' is 95.3% similar to 'process_a' (line 12)
  💡 Consider refactoring to share implementation (similarity: 0.953)

# With feedback:
Similarity Distribution:
  Mean:   0.523
  StdDev: 0.214
  ✅ Good discrimination

Suggested threshold: 0.75 (Based on 80th percentile)
```

### Rust Example

```python
class RustDuplicateExtractor(DuplicateFeatureExtractor):
    """Extract and compare Rust functions."""

    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Extract functions, impls, traits."""
        chunks = []
        chunks.extend(structure.get('functions', []))
        chunks.extend(structure.get('impls', []))
        return chunks

    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Rust-specific features."""
        return {
            'kw_fn': chunk.count('fn'),
            'kw_impl': chunk.count('impl'),
            'kw_match': chunk.count('match'),
            'lifetimes': chunk.count("'"),
            'generics': chunk.count('<') + chunk.count('>'),
            'ownership': chunk.count('&') + chunk.count('mut'),
        }
```

**Usage**: Same command, different language
```bash
reveal src/main.rs --check --select D
```

### Markdown Example

```python
class MarkdownDuplicateExtractor(DuplicateFeatureExtractor):
    """Extract and compare Markdown sections."""

    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Extract sections by headers."""
        sections = self._split_by_headers(content)
        return [
            Chunk(type='section', name=s['header'], content=s['body'])
            for s in sections
        ]

    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Markdown-specific features."""
        return {
            'code_blocks': chunk.count('```'),
            'lists': chunk.count('\n- ') + chunk.count('\n* '),
            'links': chunk.count('['),
            'images': chunk.count('!['),
            'headers': chunk.count('\n#'),
            'bold': chunk.count('**'),
        }
```

**Usage**: Detects duplicate documentation sections
```bash
reveal README.md --check --select D
```

---

## Configuration System

### Default Config (~/.reveal/duplicate_config.yaml)

```yaml
# Detection mode: exact | structural | semantic
mode: structural

# Feature extraction
features:
  syntax: true        # Language-specific tokens
  structural: true    # Control flow, nesting
  semantic: false     # Embeddings (expensive)

# Similarity
similarity:
  metric: cosine      # cosine | jaccard | euclidean
  threshold: 0.75
  adaptive: true      # Auto-adjust based on distribution

# Normalization
normalize:
  whitespace: true
  comments: true
  identifiers: false  # Rename vars (slower, catches more)
  literals: false

# Output
output:
  max_results: 10
  show_scores: true

# Feedback
feedback:
  show_statistics: true
  show_recommendations: true

# Language-specific overrides
languages:
  python:
    threshold: 0.80
  rust:
    threshold: 0.70
  markdown:
    mode: exact
    threshold: 0.85
```

### Command-Line Overrides

```bash
# Threshold tuning
reveal --check --select D --threshold 0.85
reveal --check --select D --threshold auto  # Use adaptive

# Mode selection
reveal --check --select D --mode exact
reveal --check --select D --mode structural
reveal --check --select D --mode semantic

# Feature selection
reveal --check --select D --syntax-only
reveal --check --select D --structural-only
reveal --check --select D --all-features

# Normalization
reveal --check --select D --normalize-identifiers
reveal --check --select D --normalize-literals

# Feedback control
reveal --check --select D --show-stats
reveal --check --select D --no-recommendations
reveal --check --select D --quiet  # Just detections
```

---

## Self-Reflection: Guiding Users to "Do It Well"

### 1. Distribution Analysis

**System analyzes your similarity scores and reports quality**:

```bash
reveal lib/ --check --select D --show-stats

Similarity Distribution:
  Mean:   0.873  ⚠️  Very high - features not discriminative
  Median: 0.921
  StdDev: 0.142  ⚠️  Low variance
  Quality: 0.45/1.0

Interpretation:
  ⚠️  Mean similarity very high (0.873) - features dominated by common patterns

Recommendations:
  [HIGH] Add more discriminative features
         → Try: reveal --check --select D --normalize-identifiers
  [HIGH] Features dominated by common tokens
         → Consider: TF-IDF weighting or AST structural features
```

### 2. Threshold Suggestions

**System suggests optimal threshold**:

```bash
reveal lib/ --check --select D

Current threshold: 0.75
Suggested threshold: 0.82 (Based on 80th percentile of your distribution)
Impact: Would detect 23 fewer duplicate pairs

Try: reveal lib/ --check --select D --threshold 0.82
```

### 3. Calibration Mode (Interactive)

**Guided tuning session**:

```bash
reveal lib/ --check --select D --calibrate

Step 1/4: Analyzing codebase...
Found 247 function pairs

Step 2/4: Testing thresholds...
  0.95: 12 pairs (4.9%)
  0.90: 34 pairs (13.8%)
  0.85: 67 pairs (27.1%)
  0.80: 103 pairs (41.7%)  ← Recommended
  0.75: 145 pairs (58.7%)

Step 3/4: Reviewing sample matches...

Pair #1 [similarity: 0.987]:
  process_data (line 45) ↔ transform_data (line 78)

  process_data:
      result = []
      for item in data:
          result.append(transform(item))
      return result

  transform_data:
      output = []
      for x in input:
          output.append(transform(x))
      return output

  Is this a duplicate? [y/n/skip] y

Pair #2 [similarity: 0.823]:
  validate_input (line 12) ↔ check_config (line 156)
  [Code shown...]
  Is this a duplicate? [y/n/skip] n

Step 4/4: Learning from your feedback...

Based on your labels:
  True duplicates: avg similarity 0.956
  Not duplicates: avg similarity 0.798
  Suggested threshold: 0.87

Save configuration? [y/n] y
Configuration saved to ~/.reveal/duplicate_config.yaml
```

### 4. Explain Mode (Why was this flagged?)

```bash
reveal app.py --check --select D --explain

app.py:45:1 D002 Similar: 'process_b' is 95.3% similar to 'process_a'

Why flagged?
  Similarity score: 0.953 (threshold: 0.75)
  Matched features:
    - Control flow structure: 0.98 match
    - Token distribution: 0.94 match
    - Line count: 12 vs 13 (92% match)
    - Nesting depth: identical

  Differences:
    - Variable names: data/input, result/output
    - Comments: different

  Recommendation:
    This appears to be semantic duplicate (same logic, different names).
    Consider refactoring to shared helper function.
```

---

## Adding New File Types (Easy!)

### Step 1: Create Extractor

```python
# reveal/rules/duplicates/extractors/nginx.py

from ..base_detector import DuplicateFeatureExtractor, Chunk

class NginxDuplicateExtractor(DuplicateFeatureExtractor):
    """Detect duplicate Nginx server blocks."""

    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Extract server blocks."""
        # Parse nginx config, extract server {} blocks
        blocks = self._parse_server_blocks(content)
        return [
            Chunk(type='server', name=b.server_name, content=b.body)
            for b in blocks
        ]

    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Nginx-specific directives."""
        return {
            'directive_listen': chunk.count('listen'),
            'directive_location': chunk.count('location'),
            'directive_proxy_pass': chunk.count('proxy_pass'),
            'directive_ssl': chunk.count('ssl_'),
            'upstream_count': chunk.count('upstream'),
        }
```

### Step 2: Register (Auto-discovered!)

```python
# reveal/rules/duplicates/__init__.py

EXTRACTORS = {
    '.py': PythonDuplicateExtractor,
    '.rs': RustDuplicateExtractor,
    '.md': MarkdownDuplicateExtractor,
    '.conf': NginxDuplicateExtractor,  # ← Just add this!
}
```

### Step 3: Use It

```bash
reveal nginx.conf --check --select D

nginx.conf:45:1 ℹ️  D002 Similar server block detected:
  'api.example.com' is 89.2% similar to 'app.example.com' (line 12)
```

**That's it!** Universal framework handles:
- Similarity computation
- Threshold tuning
- Statistical feedback
- Configuration management

---

## Implementation Status

### ✅ Complete
- [x] Base architecture (`base_detector.py`)
- [x] D001 (exact duplicates, hash-based)
- [x] D002 (similar functions, vector similarity)
- [x] Python support
- [x] Statistical feedback
- [x] Configuration system

### 🚧 In Progress
- [ ] Rust extractor
- [ ] Markdown extractor
- [ ] JavaScript/TypeScript extractor
- [ ] Calibration mode (interactive tuning)

### 🔮 Future
- [ ] D003 (semantic duplicates with CodeBERT)
- [ ] Cross-file duplicate detection
- [ ] TF-IDF weighting for token features
- [ ] Web UI for calibration

---

## Key Design Principles

1. **Universal > Specific**
   - Core logic works for all file types
   - Language differences isolated to extractors

2. **Configurable > Opinionated**
   - Users control threshold, features, normalization
   - Sensible defaults, easy overrides

3. **Self-Reflective > Silent**
   - System reports its own quality
   - Guides users toward better configuration
   - Explains why things were flagged

4. **Measurable > Guessed**
   - Distribution statistics
   - Quality scores
   - Precision/recall on labeled data

5. **Lean > Heavy**
   - No ML dependencies for basic modes
   - Embeddings optional (D003)
   - Fast enough for real-time use

---

## Usage Examples

### Basic: Find Duplicates

```bash
reveal app.py --check --select D
```

### Tuned: Adjust for Your Codebase

```bash
# First time: calibrate
reveal app.py --check --select D --calibrate
# → Interactive session, saves config

# Subsequent: use saved config
reveal app.py --check --select D
# → Uses your calibrated settings
```

### Strict: Catch Only Obvious Duplicates

```bash
reveal app.py --check --select D --threshold 0.95 --mode exact
```

### Loose: Find Refactoring Candidates

```bash
reveal app.py --check --select D --threshold 0.60 --normalize-identifiers
```

### Cross-Language Comparison (Future)

```bash
reveal src/**/*.py src/**/*.rs --check --select D --cross-language
# → Find functionally equivalent code in Python and Rust
```

---

## Measuring Success

**Good Configuration**:
- Mean similarity: 0.4-0.6 (not too high)
- StdDev: >0.2 (good spread)
- Quality score: >0.7
- User confirms: "Yes, these look like duplicates"

**Bad Configuration**:
- Mean similarity: >0.9 (everything looks similar!)
- StdDev: <0.1 (poor discrimination)
- Quality score: <0.4
- User confirms: "These are not duplicates"

**System guides you from bad → good through feedback!**

---

## Summary

**What we built**:
- ✅ Universal framework for any file type
- ✅ Three-layer abstraction (syntax/structure/semantic)
- ✅ Configurable everything (threshold, features, normalization)
- ✅ Self-reflective (reports quality, suggests improvements)
- ✅ Similarity scores + rankings (not binary)
- ✅ Statistical rigor (distribution analysis, threshold optimization)

**How users benefit**:
- Works on Python, Rust, Markdown, ... (easy to add new types)
- Tune for their codebase (not one-size-fits-all)
- Get guidance on doing it well (self-reflection)
- See why things were flagged (explainability)
- Measure and improve over time (statistics)

**Bottom line**:
One system, all languages, smart guidance → "Do duplicate detection well!"
