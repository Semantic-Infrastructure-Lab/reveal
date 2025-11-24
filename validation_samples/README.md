# Validation Sample Files

These files are used for manual validation testing of reveal v0.2.0.

## Quick Tests

```bash
# Python structure
reveal validation_samples/sample.py

# Extract specific function
reveal validation_samples/sample.py load_config
reveal validation_samples/sample.py DataProcessor

# Markdown sections
reveal validation_samples/sample.md
reveal validation_samples/sample.md "Features"

# YAML keys
reveal validation_samples/sample.yaml

# JSON keys
reveal validation_samples/sample.json

# Directory view
reveal validation_samples/
```

## What to Check

### Python File (sample.py)
- ✅ Shows imports (os, sys, typing, pathlib)
- ✅ Shows functions with correct signatures (e.g., `(path: str) -> Dict[str, any]`)
- ✅ Shows classes (DataProcessor)
- ✅ NO "def" prefix in signatures (this was the bug!)
- ✅ Line numbers are correct

### Markdown File (sample.md)
- ✅ Shows all headings with levels
- ✅ Section extraction works
- ✅ Nested sections handled correctly

### YAML File (sample.yaml)
- ✅ Shows top-level keys (name, version, database, services, features)
- ✅ Line numbers correct

### JSON File (sample.json)
- ✅ Shows top-level keys
- ✅ Line numbers correct

## Edge Cases to Test

```bash
# Non-existent file
reveal validation_samples/nonexistent.py
# Should error gracefully with "not found" message

# Unsupported file type
touch validation_samples/test.xyz
reveal validation_samples/test.xyz
# Should error gracefully with "No analyzer" message

# Non-existent element
reveal validation_samples/sample.py nonexistent_function
# Should error gracefully with "Element not found" message
```
