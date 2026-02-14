# Claude Adapter Guide (claude://)

**Last Updated**: 2026-02-14
**Version**: 1.0
**Adapter Version**: reveal 0.1.0+

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Features](#core-features)
4. [Elements Reference](#elements-reference)
5. [Query Parameters](#query-parameters)
6. [Progressive Disclosure Pattern](#progressive-disclosure-pattern)
7. [Tool Usage Analytics](#tool-usage-analytics)
8. [File Operation Tracking](#file-operation-tracking)
9. [Workflow Visualization](#workflow-visualization)
10. [Error Detection](#error-detection)
11. [Token Analysis](#token-analysis)
12. [Detailed Workflows](#detailed-workflows)
13. [Performance Considerations](#performance-considerations)
14. [Limitations](#limitations)
15. [Error Messages](#error-messages)
16. [Tips & Best Practices](#tips--best-practices)
17. [Integration Examples](#integration-examples)
18. [Related Documentation](#related-documentation)
19. [FAQ](#faq)

---

## Overview

The **claude://** adapter provides comprehensive analysis of Claude Code conversations, including tool usage analytics, file operation tracking, workflow visualization, and error detection. It's designed for debugging sessions, understanding agent behavior, optimizing token usage, and analyzing conversation patterns.

**Primary Use Cases**:
- Post-session review and analysis
- Debugging failed or problematic sessions
- Understanding tool usage patterns and success rates
- Tracking file operations (Read/Write/Edit)
- Identifying errors with full context
- Optimizing token usage
- Analyzing agent workflows
- Extracting thinking blocks for analysis

**Key Capabilities**:
- Session overview with message counts, tool usage, duration
- Tool usage analytics with success rates
- File operation tracking (Read/Write/Edit operations)
- Chronological workflow visualization
- Error detection with full context
- Thinking block extraction and token estimates
- Context change tracking (directory, branch changes)
- Composite query support (filter by tools, errors, text, role)

**Design Philosophy**:
- **Progressive disclosure**: Start with overview, drill down as needed
- **Token-efficient**: Avoid loading full conversations unless necessary
- **Composable queries**: Combine filters for precise analysis
- **Actionable insights**: Tool success rates, error context, optimization recommendations

---

## Quick Start

### 1. Session Overview

Get high-level session summary (messages, tools, duration):

```bash
reveal claude://session/infernal-earth-0118
```

**Returns**: Session name, message count, tool calls, duration, tool summary, next steps

### 2. Session Summary

Get comprehensive summary with key events:

```bash
reveal claude://session/infernal-earth-0118?summary
```

**Returns**: Overview + timeline + critical events + recommendations

### 3. Tool Usage Analysis

Get all tool usage with success rates:

```bash
reveal claude://session/infernal-earth-0118/tools
```

**Returns**: Tool usage counts, success rates, common operations

### 4. File Operations

Track all files read, written, or edited:

```bash
reveal claude://session/infernal-earth-0118/files
```

**Returns**: File paths, operation types (Read/Write/Edit), access counts

### 5. Workflow Visualization

See chronological sequence of tool operations:

```bash
reveal claude://session/infernal-earth-0118/workflow
```

**Returns**: Time-ordered tool calls with parameters and results

### 6. Error Detection

Find all errors with context:

```bash
reveal claude://session/infernal-earth-0118?errors
```

**Returns**: Error messages, message IDs, surrounding context

### 7. Thinking Block Analysis

Extract all thinking blocks:

```bash
reveal claude://session/infernal-earth-0118/thinking
```

**Returns**: All thinking blocks with token estimates and analysis

### 8. Filter by Tool

Show only specific tool usage:

```bash
reveal claude://session/infernal-earth-0118?tools=Bash
reveal claude://session/infernal-earth-0118?tools=Read
```

**Returns**: Filtered messages/operations for specified tool

---

## Core Features

### 1. Progressive Disclosure

Start with overview, drill down as needed:

```bash
# Level 1: Overview (token-efficient)
reveal claude://session/my-session

# Level 2: Specific analysis
reveal claude://session/my-session/tools      # Tool usage
reveal claude://session/my-session/files      # File operations
reveal claude://session/my-session/workflow   # Chronological flow

# Level 3: Deep analysis
reveal claude://session/my-session?errors     # Error debugging
reveal claude://session/my-session/thinking   # Token analysis
reveal claude://session/my-session?tools=Bash # Tool-specific
```

**Why**: Prevents loading full conversations unnecessarily, saves tokens

---

### 2. Tool Usage Analytics

Track and analyze tool usage patterns:

**Metrics provided**:
- **Tool counts**: How many times each tool was called
- **Success rates**: Percentage of successful tool calls
- **Common operations**: Most frequent operations per tool
- **Tool pairs**: Which tools are commonly used together

**Example output**:
```json
{
  "type": "claude_tools",
  "session_name": "infernal-earth-0118",
  "tools": [
    {
      "name": "Read",
      "count": 15,
      "success_rate": 93.3,
      "common_operations": [
        "/path/to/file.py (5 times)",
        "/path/to/config.yaml (3 times)"
      ]
    },
    {
      "name": "Bash",
      "count": 8,
      "success_rate": 87.5,
      "common_operations": [
        "git status",
        "pytest tests/"
      ]
    }
  ],
  "overall_success_rate": 91.2
}
```

**Use cases**:
- Identify unreliable tools (low success rates)
- Find frequently used operations (optimization targets)
- Understand agent behavior patterns
- Debug tool failures

---

### 3. File Operation Tracking

Track all file access patterns:

**Operations tracked**:
- **Read**: Files inspected during session
- **Write**: Files created from scratch
- **Edit**: Files modified (existing content changed)

**Metrics provided**:
- File paths and operation types
- Access frequency (how many times each file was touched)
- Operation distribution (Read vs Write vs Edit)

**Example output**:
```json
{
  "type": "claude_files",
  "session_name": "infernal-earth-0118",
  "files": [
    {
      "path": "/home/user/project/src/main.py",
      "operations": ["Read", "Edit"],
      "access_count": 3
    },
    {
      "path": "/home/user/project/tests/test_main.py",
      "operations": ["Write"],
      "access_count": 1
    }
  ],
  "summary": {
    "total_files": 12,
    "read_only": 7,
    "modified": 4,
    "created": 1
  }
}
```

**Use cases**:
- Track what files were touched during debugging
- Identify hotspots (frequently modified files)
- Verify expected file operations occurred
- Document changes for review

---

### 4. Workflow Visualization

Chronological sequence of tool operations:

**What it shows**:
- Time-ordered tool calls (first to last)
- Tool names and parameters
- Results (success/failure)
- Execution flow patterns

**Example output**:
```json
{
  "type": "claude_workflow",
  "session_name": "infernal-earth-0118",
  "operations": [
    {
      "step": 1,
      "timestamp": "2026-01-18T10:15:23",
      "tool": "Read",
      "params": {"file_path": "/path/to/file.py"},
      "result": "success"
    },
    {
      "step": 2,
      "timestamp": "2026-01-18T10:16:45",
      "tool": "Edit",
      "params": {"file_path": "/path/to/file.py", "old_string": "...", "new_string": "..."},
      "result": "success"
    },
    {
      "step": 3,
      "timestamp": "2026-01-18T10:17:30",
      "tool": "Bash",
      "params": {"command": "pytest tests/"},
      "result": "failure",
      "error": "Test failed: AssertionError"
    }
  ]
}
```

**Use cases**:
- Understand sequence of operations
- Identify where session went wrong
- Analyze problem-solving patterns
- Document agent workflow for optimization

---

### 5. Error Detection

Find errors with full context:

**What it detects**:
- Tool call failures
- Exception messages
- Error responses
- Context around errors (surrounding messages)

**Example output**:
```json
{
  "type": "claude_errors",
  "session_name": "infernal-earth-0118",
  "count": 2,
  "errors": [
    {
      "message_id": 67,
      "tool": "Bash",
      "error": "Command failed with exit code 1",
      "command": "pytest tests/",
      "context": {
        "previous_message": "Running tests...",
        "next_message": "Test failed, investigating..."
      }
    },
    {
      "message_id": 89,
      "tool": "Edit",
      "error": "Pattern not found in file",
      "file": "/path/to/file.py",
      "pattern": "def old_function"
    }
  ]
}
```

**Use cases**:
- Debug failed sessions
- Identify recurring errors
- Find root causes of failures
- Optimize error handling patterns

---

### 6. Thinking Block Extraction

Extract and analyze all thinking blocks:

**What it provides**:
- All thinking blocks from session
- Token estimates (chars / 4)
- Thinking patterns analysis
- Token optimization insights

**Example output**:
```json
{
  "type": "claude_thinking",
  "session_name": "infernal-earth-0118",
  "thinking_blocks": [
    {
      "message_id": 12,
      "content": "Let me analyze this error...",
      "token_estimate": 156,
      "length_chars": 624
    },
    {
      "message_id": 34,
      "content": "I need to check if...",
      "token_estimate": 89,
      "length_chars": 356
    }
  ],
  "total_thinking_tokens": 245,
  "analysis": {
    "avg_thinking_block_size": 122,
    "largest_thinking_block": 156,
    "thinking_frequency": "High"
  }
}
```

**Use cases**:
- Understand agent reasoning process
- Identify token waste in thinking blocks
- Optimize thinking patterns
- Debug reasoning failures

---

### 7. Context Change Tracking

Track directory and branch changes during session:

**What it tracks**:
- Working directory changes (cd commands)
- Git branch changes (git checkout, git switch)
- Repository switches

**Example output**:
```json
{
  "type": "claude_context",
  "session_name": "infernal-earth-0118",
  "context_changes": [
    {
      "type": "directory",
      "from": "/home/user/project",
      "to": "/home/user/project/tests",
      "message_id": 23
    },
    {
      "type": "branch",
      "from": "main",
      "to": "feature/new-api",
      "message_id": 45
    }
  ]
}
```

**Use cases**:
- Track context switches during debugging
- Understand agent navigation patterns
- Identify context confusion issues

---

### 8. Composite Queries

Combine filters for precise analysis:

```bash
# Bash tool usage + errors only
reveal claude://session/my-session?tools=Bash&errors

# User messages containing specific text
reveal claude://session/my-session?role=user&contains=reveal

# Summary with error focus
reveal claude://session/my-session?summary&errors
```

**Supported combinations**:
- `?tools=<tool>&errors` - Specific tool failures
- `?role=<role>&contains=<text>` - Role-filtered text search
- `?summary&errors` - Summary with error emphasis
- `?tools=<tool>&contains=<text>` - Tool usage with text filter

---

## Elements Reference

The claude:// adapter supports seven elements for progressive disclosure:

### 1. workflow

**Description**: Chronological sequence of tool operations

**Syntax**:
```bash
reveal claude://session/<session-name>/workflow
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/workflow
```

**Output**: Time-ordered tool calls with parameters, results, and execution flow

**Use when**: Need to understand sequence of operations, debug workflow issues

---

### 2. files

**Description**: All files read, written, or edited during session

**Syntax**:
```bash
reveal claude://session/<session-name>/files
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/files
```

**Output**: File paths, operation types (Read/Write/Edit), access counts, summary metrics

**Use when**: Track file modifications, identify hotspots, verify expected operations

---

### 3. tools

**Description**: Tool usage analytics with success rates

**Syntax**:
```bash
reveal claude://session/<session-name>/tools
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/tools
```

**Output**: Tool counts, success rates, common operations, overall success rate

**Use when**: Analyze tool usage patterns, identify unreliable tools, optimize operations

---

### 4. thinking

**Description**: All thinking blocks with token estimates

**Syntax**:
```bash
reveal claude://session/<session-name>/thinking
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/thinking
```

**Output**: Thinking block content, token estimates, analysis, optimization insights

**Use when**: Understand agent reasoning, identify token waste, optimize thinking patterns

---

### 5. errors

**Description**: All errors and exceptions with full context

**Syntax**:
```bash
reveal claude://session/<session-name>/errors
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/errors
```

**Output**: Error messages, message IDs, tool names, surrounding context

**Use when**: Debug session failures, identify recurring errors, find root causes

---

### 6. timeline

**Description**: Chronological message timeline

**Syntax**:
```bash
reveal claude://session/<session-name>/timeline
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/timeline
```

**Output**: Message sequence with timestamps, roles, brief content summaries

**Use when**: Understand conversation flow, identify timing patterns

---

### 7. context

**Description**: Context window changes over session (directory, branch changes)

**Syntax**:
```bash
reveal claude://session/<session-name>/context
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118/context
```

**Output**: Directory changes, branch switches, repository changes

**Use when**: Track context switches, debug navigation issues, understand agent context management

---

## Query Parameters

### ?summary

**Description**: Session summary with key events and recommendations

**Syntax**:
```bash
reveal claude://session/<session-name>?summary
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118?summary
```

**Output**: Overview + timeline + critical events + recommendations

**Use when**: Quick session understanding, post-session review

---

### ?errors

**Description**: Filter for messages containing errors

**Syntax**:
```bash
reveal claude://session/<session-name>?errors
```

**Example**:
```bash
reveal claude://session/infernal-earth-0118?errors
```

**Output**: Only messages with errors, error context, error summary

**Use when**: Debug failed sessions, focus on problems

---

### ?tools=<tool>

**Description**: Filter for specific tool usage

**Syntax**:
```bash
reveal claude://session/<session-name>?tools=<ToolName>
```

**Examples**:
```bash
reveal claude://session/infernal-earth-0118?tools=Bash
reveal claude://session/infernal-earth-0118?tools=Read
reveal claude://session/infernal-earth-0118?tools=Edit
```

**Output**: Only messages/operations involving specified tool

**Use when**: Analyze specific tool behavior, debug tool-specific issues

---

### ?contains=<text>

**Description**: Filter messages containing specific text

**Syntax**:
```bash
reveal claude://session/<session-name>?contains=<text>
```

**Examples**:
```bash
reveal claude://session/infernal-earth-0118?contains=reveal
reveal claude://session/infernal-earth-0118?contains=error
reveal claude://session/infernal-earth-0118?contains="import pandas"
```

**Output**: Only messages containing specified text (case-insensitive)

**Use when**: Find specific topics, track keyword usage, search conversations

---

### ?role=<role>

**Description**: Filter by message role (user or assistant)

**Syntax**:
```bash
reveal claude://session/<session-name>?role=<role>
```

**Examples**:
```bash
reveal claude://session/infernal-earth-0118?role=user
reveal claude://session/infernal-earth-0118?role=assistant
```

**Output**: Only messages from specified role

**Use when**: Analyze user requests, track agent responses

---

### Composite Queries

Combine multiple query parameters:

```bash
# Bash errors
reveal claude://session/my-session?tools=Bash&errors

# User messages about reveal
reveal claude://session/my-session?role=user&contains=reveal

# Summary with error emphasis
reveal claude://session/my-session?summary&errors

# Read operations with errors
reveal claude://session/my-session?tools=Read&errors
```

---

## Progressive Disclosure Pattern

The claude:// adapter uses **progressive disclosure** to provide exactly the level of detail needed:

### Level 1: Overview (Token-Efficient)

**Command**:
```bash
reveal claude://session/my-session
```

**Token cost**: ~300-500 tokens

**Returns**:
- Session name
- Message count
- Tool call count
- Duration
- Tool summary (top tools with counts)
- Next steps

**Use when**: Initial session assessment, quick status check

---

### Level 2: Specific Analysis (Moderate Detail)

**Commands**:
```bash
reveal claude://session/my-session/tools      # Tool analytics
reveal claude://session/my-session/files      # File operations
reveal claude://session/my-session/workflow   # Operation sequence
```

**Token cost**: ~500-1000 tokens per element

**Returns**: Complete data for requested analysis type

**Use when**: Need specific aspect understanding

---

### Level 3: Filtered Analysis (Targeted Detail)

**Commands**:
```bash
reveal claude://session/my-session?errors           # Only errors
reveal claude://session/my-session?tools=Bash       # Only Bash usage
reveal claude://session/my-session?contains=reveal  # Text search
```

**Token cost**: ~400-800 tokens (depends on filter match count)

**Returns**: Filtered messages/operations matching criteria

**Use when**: Debugging specific issues, targeted analysis

---

### Level 4: Deep Analysis (Comprehensive)

**Commands**:
```bash
reveal claude://session/my-session?summary          # Full summary
reveal claude://session/my-session/thinking         # All thinking blocks
reveal claude://session/my-session?tools=Bash&errors # Composite filter
```

**Token cost**: ~1000-2000 tokens

**Returns**: Comprehensive analysis with insights and recommendations

**Use when**: Deep understanding needed, optimization analysis, comprehensive review

---

### Pattern Summary

```
Overview (300 tokens)
   ↓
Specific analysis (500 tokens)
   ↓
Filtered analysis (600 tokens)
   ↓
Deep analysis (1500 tokens)
```

**Rule**: Start shallow, drill down only when needed

---

## Tool Usage Analytics

### Success Rate Calculation

**Formula**:
```
Success Rate = (Successful Calls / Total Calls) × 100
```

**Determination**:
- **Success**: Tool result returned without error
- **Failure**: Tool result contains error or exception

**Example**:
```json
{
  "name": "Bash",
  "count": 10,
  "successful": 8,
  "failed": 2,
  "success_rate": 80.0
}
```

---

### Common Tool Patterns

**Read tool patterns**:
```json
{
  "name": "Read",
  "count": 15,
  "common_operations": [
    "/path/to/config.yaml (5 times)",
    "/path/to/main.py (3 times)",
    "/path/to/tests/*.py (2 times)"
  ]
}
```

**Bash tool patterns**:
```json
{
  "name": "Bash",
  "count": 12,
  "common_operations": [
    "git status (4 times)",
    "pytest tests/ (3 times)",
    "ls -la (2 times)"
  ]
}
```

**Edit tool patterns**:
```json
{
  "name": "Edit",
  "count": 8,
  "common_operations": [
    "main.py: function refactor (3 times)",
    "config.yaml: value update (2 times)"
  ]
}
```

---

### Tool Success Rate Thresholds

| Success Rate | Status | Action |
|--------------|--------|--------|
| **90-100%** | Excellent | No action needed |
| **75-89%** | Good | Monitor for patterns |
| **50-74%** | Fair | Investigate failures |
| **< 50%** | Poor | Review usage patterns, consider alternatives |

---

### Tool Usage Insights

**High Read tool usage**: Might indicate:
- Heavy file inspection (normal for debugging)
- Repeated file reads (optimization opportunity)
- Missing context (agent re-reading same files)

**High Bash tool failures**: Might indicate:
- Command syntax issues
- Environment problems
- Permission issues

**High Edit tool failures**: Might indicate:
- Pattern matching issues (old_string not found)
- File conflicts (file changed between read and edit)
- Incorrect file paths

---

## File Operation Tracking

### Operation Types

**Read operations**:
- **Purpose**: Inspect file contents
- **Typical count**: High (5-20 reads per session)
- **Pattern**: Often repeated for same files

**Write operations**:
- **Purpose**: Create new files
- **Typical count**: Low (0-3 writes per session)
- **Pattern**: Concentrated during implementation

**Edit operations**:
- **Purpose**: Modify existing files
- **Typical count**: Moderate (2-8 edits per session)
- **Pattern**: Iterative refinement

---

### File Access Patterns

**Hotspot detection**:
```json
{
  "path": "/home/user/project/src/main.py",
  "operations": ["Read", "Read", "Edit", "Read", "Edit"],
  "access_count": 5,
  "pattern": "Heavy modification (3 reads + 2 edits)"
}
```

**Hotspot interpretation**:
- **access_count > 5**: Potential hotspot, consider why file needs repeated access
- **Multiple edits**: Iterative refinement (normal) or indecision (review needed)
- **Read-only with high count**: Reference file or missing information

---

### File Coverage Analysis

**Metrics**:
```json
{
  "summary": {
    "total_files": 15,
    "read_only": 10,
    "modified": 4,
    "created": 1
  }
}
```

**Interpretation**:
- **High read_only count**: Exploratory session, debugging, learning
- **High modified count**: Implementation session, bug fixing
- **High created count**: Feature development, scaffolding

---

## Workflow Visualization

### Operation Sequence Analysis

**Linear workflow** (typical):
```
Read → Edit → Bash (test) → Read (verify) → Edit (fix) → Bash (test) ✓
```

**Iterative workflow** (debugging):
```
Read → Bash (test) ✗ → Read → Edit → Bash (test) ✗ → Read → Edit → Bash (test) ✓
```

**Exploratory workflow** (investigation):
```
Read → Read → Read → Bash (check) → Read → Read → Bash (analyze)
```

---

### Workflow Patterns

**Pattern 1: Test-Driven Development**
```
Write (test) → Write (impl) → Bash (pytest) → Edit (fix) → Bash (pytest) ✓
```

**Pattern 2: Iterative Refinement**
```
Read → Edit → Bash (check) → Edit → Bash (check) → Edit → Bash (check) ✓
```

**Pattern 3: Debugging**
```
Bash (reproduce) → Read (investigate) → Edit (fix) → Bash (verify) ✓
```

**Pattern 4: Exploration**
```
Read → Read → Read → Bash (analyze) → Read → Write (summary)
```

---

### Workflow Insights

**Fast convergence** (3-5 steps):
- Clear understanding of problem
- Effective tool selection
- Minimal trial-and-error

**Slow convergence** (10+ steps):
- Unclear problem definition
- Repeated operations (optimization opportunity)
- Trial-and-error approach (consider planning first)

---

## Error Detection

### Error Types

**Tool call errors**:
- Bash command failures (exit code != 0)
- Edit pattern not found
- Read file not found
- Permission denied

**System errors**:
- Timeout
- Network errors
- Resource exhaustion

**Logic errors**:
- Test failures
- Assertion errors
- Validation failures

---

### Error Context

Each error includes:
- **Message ID**: Where error occurred
- **Tool name**: Which tool failed
- **Error message**: Specific error text
- **Context**: Surrounding messages (before/after)

**Example**:
```json
{
  "message_id": 67,
  "tool": "Bash",
  "error": "Command failed with exit code 1",
  "command": "pytest tests/test_main.py",
  "context": {
    "previous": "Running tests to verify fix...",
    "next": "Test failed: AssertionError on line 45"
  }
}
```

---

### Error Analysis

**Recurring errors**: Same error multiple times
- **Indicates**: Misunderstanding, environment issue, incorrect approach
- **Action**: Review error pattern, check environment, consider alternative approach

**Cascading errors**: One error triggers others
- **Indicates**: Root cause issue
- **Action**: Focus on first error in sequence

**Isolated errors**: Single error, then recovery
- **Indicates**: Normal trial-and-error, environment glitch
- **Action**: Usually no concern unless recurring

---

## Token Analysis

### Token Estimation

**Formula**: `tokens ≈ characters / 4`

**Accuracy**: ±10% (approximation, actual tokenization varies)

---

### Thinking Block Analysis

**Metrics**:
- Total thinking tokens
- Average thinking block size
- Largest thinking block
- Thinking frequency (High/Medium/Low)

**Example**:
```json
{
  "total_thinking_tokens": 1245,
  "avg_block_size": 156,
  "largest_block": 523,
  "frequency": "High"
}
```

---

### Token Optimization Insights

**High thinking token usage** (>30% of session):
- **Potential issue**: Over-analysis, repetitive thinking
- **Action**: Consider more direct approaches, reduce unnecessary reasoning

**Large thinking blocks** (>500 tokens):
- **Potential issue**: Complex reasoning chains
- **Action**: Review if complexity is justified, consider breaking down problem

**Frequent thinking blocks** (>20 blocks):
- **Potential issue**: Excessive internal deliberation
- **Action**: Improve prompt clarity, provide more context upfront

---

## Detailed Workflows

### Workflow 1: Post-Session Review

**Scenario**: Understand what happened in a completed session

**Steps**:

```bash
# Step 1: Quick overview
reveal claude://session/my-session
# Returns: Message count, tool usage, duration, summary

# Step 2: Check for errors
reveal claude://session/my-session?errors
# Returns: Any errors that occurred

# Step 3: Analyze tool usage
reveal claude://session/my-session/tools
# Returns: Tool counts, success rates

# Step 4: Review file operations
reveal claude://session/my-session/files
# Returns: Files modified, created, read

# Step 5: Comprehensive summary
reveal claude://session/my-session?summary
# Returns: Full summary with recommendations
```

**Automation**:
```bash
#!/bin/bash
SESSION="$1"
echo "=== Session Overview ==="
reveal claude://session/$SESSION

echo -e "\n=== Errors ==="
reveal claude://session/$SESSION?errors

echo -e "\n=== Tool Usage ==="
reveal claude://session/$SESSION/tools

echo -e "\n=== Files Modified ==="
reveal claude://session/$SESSION/files
```

---

### Workflow 2: Debug Failed Session

**Scenario**: Find why a session failed and what went wrong

**Steps**:

```bash
# Step 1: Check for errors
reveal claude://session/failed-build?errors
# Returns: All errors with context

# Step 2: View workflow to find failure point
reveal claude://session/failed-build/workflow
# Returns: Chronological operations, identifies where failure occurred

# Step 3: Check specific tool failures
reveal claude://session/failed-build?tools=Bash&errors
# Returns: Bash command failures specifically

# Step 4: Review error context
reveal claude://session/failed-build/errors
# Returns: Detailed error information with surrounding messages

# Step 5: Analyze tool success rates
reveal claude://session/failed-build/tools
# Returns: Which tools had issues
```

---

### Workflow 3: Token Optimization

**Scenario**: Identify token waste and optimize session efficiency

**Steps**:

```bash
# Step 1: Get summary with token estimates
reveal claude://session/my-session?summary
# Returns: Overview with token usage patterns

# Step 2: Analyze thinking blocks
reveal claude://session/my-session/thinking
# Returns: All thinking blocks with token estimates

# Step 3: Check for repeated Read operations
reveal claude://session/my-session?tools=Read
# Returns: All Read operations (look for duplicates)

# Step 4: Identify file hotspots
reveal claude://session/my-session/files
# Returns: Files with high access counts (optimization targets)
```

**Optimization recommendations**:
- **Repeated reads of same file**: Use context management, pass context explicitly
- **Large thinking blocks**: Simplify prompts, provide clearer direction
- **High file access count**: Consider summarizing or caching file content

---

### Workflow 4: Agent Behavior Analysis

**Scenario**: Understand how agent approached a problem

**Steps**:

```bash
# Step 1: View workflow sequence
reveal claude://session/my-session/workflow
# Returns: Chronological tool operations

# Step 2: Analyze tool selection
reveal claude://session/my-session/tools
# Returns: Which tools were chosen and how often

# Step 3: Track context changes
reveal claude://session/my-session/context
# Returns: Directory and branch changes

# Step 4: Review thinking process
reveal claude://session/my-session/thinking
# Returns: Agent reasoning and decision-making
```

---

### Workflow 5: Session Comparison

**Scenario**: Compare two sessions (e.g., successful vs failed)

**Steps**:

```bash
# Session 1 analysis
reveal claude://session/successful-session/tools > session1-tools.json
reveal claude://session/successful-session/workflow > session1-workflow.json

# Session 2 analysis
reveal claude://session/failed-session/tools > session2-tools.json
reveal claude://session/failed-session/workflow > session2-workflow.json

# Compare with diff
diff -u session1-tools.json session2-tools.json
diff -u session1-workflow.json session2-workflow.json
```

**Analysis**:
- Tool usage differences
- Workflow pattern differences
- Success rate differences

---

### Workflow 6: Continuous Monitoring

**Scenario**: Track session quality over time

**Setup monitoring script**:

```bash
#!/bin/bash
# monitor-sessions.sh

SESSION_DIR="$HOME/.claude/projects/my-project"

for session in $(ls -1t $SESSION_DIR | head -10); do
  echo "=== $session ==="

  # Get success rate
  SUCCESS_RATE=$(reveal claude://session/$session/tools --format json | \
    jq -r '.overall_success_rate')

  # Get error count
  ERROR_COUNT=$(reveal claude://session/$session?errors --format json | \
    jq -r '.count // 0')

  echo "Success Rate: $SUCCESS_RATE%"
  echo "Errors: $ERROR_COUNT"

  # Alert if issues
  if (( $(echo "$SUCCESS_RATE < 80" | bc -l) )) || [ "$ERROR_COUNT" -gt 5 ]; then
    echo "⚠️  Session quality issues detected"
  fi

  echo ""
done
```

---

## Performance Considerations

### Operation Timing

| Operation | Typical Duration | Notes |
|-----------|-----------------|-------|
| Overview | 0.1-0.3s | Fast (metadata extraction) |
| Tools analysis | 0.2-0.5s | Fast (tool call parsing) |
| Files analysis | 0.2-0.5s | Fast (file operation parsing) |
| Workflow | 0.3-0.8s | Moderate (full operation sequence) |
| Errors | 0.1-0.4s | Fast (error pattern matching) |
| Thinking | 0.2-0.6s | Moderate (thinking block extraction) |
| Summary | 0.5-1.2s | Slower (comprehensive analysis) |

---

### Optimization Strategies

#### 1. Progressive Disclosure

Start with overview, drill down only when needed:

```bash
# ❌ Expensive: Jump to comprehensive analysis
reveal claude://session/my-session?summary

# ✅ Efficient: Start with overview
reveal claude://session/my-session
# If issues detected:
reveal claude://session/my-session?errors
# If deeper analysis needed:
reveal claude://session/my-session?summary
```

**Token savings**: 60-70%

---

#### 2. Targeted Filtering

Use filters to reduce output:

```bash
# ❌ Large output: All messages
reveal claude://session/my-session

# ✅ Focused: Only Bash usage
reveal claude://session/my-session?tools=Bash

# ✅ Even more focused: Bash errors only
reveal claude://session/my-session?tools=Bash&errors
```

**Output reduction**: 80-90%

---

#### 3. Element Selection

Choose specific elements instead of full summary:

```bash
# ❌ Heavy: Full summary
reveal claude://session/my-session?summary

# ✅ Light: Just what you need
reveal claude://session/my-session/tools  # Only tool analytics
reveal claude://session/my-session/files  # Only file operations
```

**Performance gain**: 2-3x faster

---

#### 4. JSON Output for Automation

Use JSON format for programmatic analysis:

```bash
# Parse with jq for efficient filtering
reveal claude://session/my-session/tools --format json | jq '.tools[] | select(.success_rate < 80)'
```

**Benefit**: Client-side filtering, reduced output, easier parsing

---

## Limitations

### Current Limitations

1. **Conversation file dependency**
   - **Requirement**: Conversation JSONL file must exist in `~/.claude/projects/`
   - **Impact**: Can't analyze sessions without saved conversations
   - **Workaround**: Ensure conversations are saved

2. **Session name matching**
   - **Limitation**: Session name must match directory name pattern
   - **Impact**: Non-standard session names may not be found
   - **Workaround**: Use exact session name from directory listing

3. **Token estimation accuracy**
   - **Limitation**: Approximation (chars / 4), not exact tokenization
   - **Accuracy**: ±10%
   - **Impact**: Token counts are estimates, not precise
   - **Workaround**: Use for relative comparison, not absolute values

4. **No live session analysis**
   - **Limitation**: Only analyzes completed conversation files
   - **Impact**: Can't analyze current/ongoing session
   - **Workaround**: Wait for session to complete and save

5. **No session modification**
   - **Limitation**: Read-only analysis (can't edit conversations)
   - **Design**: Intentional (inspection tool, not editor)

6. **Limited message indexing**
   - **Limitation**: No full-text search across all sessions
   - **Impact**: Must analyze one session at a time
   - **Workaround**: Use shell loops for multi-session analysis

---

### Design Limitations (Intentional)

1. **No conversation editing**: Read-only (by design)
2. **No cross-session analysis**: One session at a time (by design)
3. **No real-time monitoring**: File-based analysis only (by design)

---

## Error Messages

### Common Errors and Solutions

#### Error: "Session not found"

**Meaning**: Conversation file doesn't exist for specified session

**Solutions**:
```bash
# Check session directory exists
ls ~/.claude/projects/my-project/

# List available sessions
reveal claude://session/list

# Verify session name spelling
```

---

#### Error: "Invalid session name"

**Meaning**: Session name format not recognized

**Solutions**:
- Use exact session name from directory (e.g., "infernal-earth-0118")
- Check for typos
- Ensure session name matches directory name pattern

---

#### Error: "Conversation file not found"

**Meaning**: Session directory exists but no conversation.jsonl file

**Solutions**:
```bash
# Check if conversation file exists
ls ~/.claude/projects/my-project/infernal-earth-0118/conversation.jsonl

# Ensure session completed and saved
```

---

#### Error: "Invalid JSON in conversation file"

**Meaning**: Conversation file corrupted or malformed

**Solutions**:
```bash
# Check file integrity
jq . ~/.claude/projects/my-project/session/conversation.jsonl

# If corrupted, file may need recovery from backups
```

---

## Tips & Best Practices

### 1. Start with Overview, Then Drill Down

```bash
# ❌ Wasteful: Jump to deep analysis
reveal claude://session/my-session?summary

# ✅ Efficient: Progressive disclosure
reveal claude://session/my-session              # Overview
# If issues detected:
reveal claude://session/my-session?errors       # Focus on problems
# If deeper understanding needed:
reveal claude://session/my-session/workflow     # Full sequence
```

**Token savings**: 60-70%

---

### 2. Use Filters for Targeted Analysis

```bash
# ✅ Focus on specific tool
reveal claude://session/my-session?tools=Bash

# ✅ Find errors only
reveal claude://session/my-session?errors

# ✅ Combine filters
reveal claude://session/my-session?tools=Bash&errors
```

**Benefit**: Reduced noise, faster analysis

---

### 3. Analyze Tool Success Rates

```bash
# Check overall tool health
reveal claude://session/my-session/tools

# Tools with <80% success rate need investigation
```

**Action items**:
- <50% success rate: Review usage patterns, consider alternatives
- 50-80%: Investigate common failures
- >80%: Acceptable, monitor for trends

---

### 4. Track File Hotspots

```bash
# Identify frequently accessed files
reveal claude://session/my-session/files
```

**High access count (>5)**:
- **Why**: Complex file, unclear structure, repeated exploration
- **Action**: Consider summarizing, improving documentation, caching content

---

### 5. Review Workflow for Patterns

```bash
# Understand operation sequence
reveal claude://session/my-session/workflow
```

**Look for**:
- Repeated operations (optimization opportunity)
- Failed operation sequences (debugging patterns)
- Inefficient patterns (Read → Edit → Read → Edit instead of Read → Edit)

---

### 6. Use JSON Output for Automation

```bash
# Extract success rates
reveal claude://session/my-session/tools --format json | \
  jq '.tools[] | select(.success_rate < 80)'

# Extract error messages
reveal claude://session/my-session?errors --format json | \
  jq '.errors[].error'

# Count specific tool usage
reveal claude://session/my-session/tools --format json | \
  jq '.tools[] | select(.name == "Bash") | .count'
```

---

### 7. Compare Sessions for Quality Trends

```bash
#!/bin/bash
# Compare success rates across recent sessions

for session in $(ls -1t ~/.claude/projects/my-project | head -5); do
  RATE=$(reveal claude://session/$session/tools --format json | jq -r '.overall_success_rate')
  echo "$session: $RATE%"
done
```

---

### 8. Analyze Thinking Blocks for Token Optimization

```bash
# Find excessive thinking
reveal claude://session/my-session/thinking --format json | \
  jq '.thinking_blocks[] | select(.token_estimate > 500)'
```

**If thinking tokens >30% of session**: Consider clearer prompts, more context upfront

---

### 9. Document Session Patterns

```bash
# Generate session report
{
  echo "# Session: my-session"
  echo ""
  echo "## Overview"
  reveal claude://session/my-session
  echo ""
  echo "## Tool Usage"
  reveal claude://session/my-session/tools
  echo ""
  echo "## Files Modified"
  reveal claude://session/my-session/files
} > session-report.md
```

---

### 10. Monitor Error Patterns Over Time

```bash
#!/bin/bash
# Track error trends

ERROR_LOG="error-trends.csv"
echo "Date,Session,Error Count,Success Rate" > $ERROR_LOG

for session in $(ls -1t ~/.claude/projects/my-project | head -20); do
  ERRORS=$(reveal claude://session/$session?errors --format json | jq -r '.count // 0')
  SUCCESS=$(reveal claude://session/$session/tools --format json | jq -r '.overall_success_rate // 0')
  DATE=$(stat -c %y ~/.claude/projects/my-project/$session | cut -d' ' -f1)

  echo "$DATE,$session,$ERRORS,$SUCCESS" >> $ERROR_LOG
done

echo "Error trends logged to $ERROR_LOG"
```

---

## Integration Examples

### 1. jq Integration

**Extract tool success rates**:
```bash
reveal claude://session/my-session/tools --format json | \
  jq '.tools[] | {name, success_rate}'
```

**Find low-success tools**:
```bash
reveal claude://session/my-session/tools --format json | \
  jq '.tools[] | select(.success_rate < 80)'
```

**Count errors**:
```bash
reveal claude://session/my-session?errors --format json | jq '.count'
```

**Extract file paths**:
```bash
reveal claude://session/my-session/files --format json | jq -r '.files[].path'
```

---

### 2. Python Integration

```python
import subprocess
import json

def analyze_session(session_name):
    """Analyze session and return metrics."""
    result = subprocess.run(
        ['reveal', f'claude://session/{session_name}/tools', '--format', 'json'],
        capture_output=True,
        text=True
    )

    data = json.loads(result.stdout)

    return {
        'session': session_name,
        'overall_success_rate': data['overall_success_rate'],
        'tool_count': len(data['tools']),
        'low_success_tools': [
            tool['name'] for tool in data['tools']
            if tool['success_rate'] < 80
        ]
    }

# Analyze session
metrics = analyze_session('infernal-earth-0118')
print(f"Session: {metrics['session']}")
print(f"Success Rate: {metrics['overall_success_rate']}%")
if metrics['low_success_tools']:
    print(f"⚠️  Low-success tools: {', '.join(metrics['low_success_tools'])}")
```

---

### 3. Shell Script Integration

**Session quality report**:

```bash
#!/bin/bash
# session-report.sh - Generate session quality report

SESSION="$1"

if [ -z "$SESSION" ]; then
  echo "Usage: $0 <session-name>"
  exit 1
fi

echo "=== Session Quality Report: $SESSION ==="
echo ""

# Overview
echo "## Overview"
reveal claude://session/$SESSION

# Tool success rates
echo -e "\n## Tool Success Rates"
reveal claude://session/$SESSION/tools --format json | \
  jq -r '.tools[] | "\(.name): \(.success_rate)%"'

# Error count
echo -e "\n## Errors"
ERROR_COUNT=$(reveal claude://session/$SESSION?errors --format json | jq -r '.count // 0')
echo "Total errors: $ERROR_COUNT"

if [ "$ERROR_COUNT" -gt 0 ]; then
  echo "Error details:"
  reveal claude://session/$SESSION?errors --format json | \
    jq -r '.errors[] | "  - [\(.tool)] \(.error)"'
fi

# File operations
echo -e "\n## File Operations"
reveal claude://session/$SESSION/files --format json | \
  jq -r '.summary | "Total files: \(.total_files), Modified: \(.modified), Created: \(.created)"'

echo ""
echo "Report complete."
```

---

### 4. Monitoring Dashboard

**Track session health**:

```bash
#!/bin/bash
# dashboard.sh - Live session quality dashboard

PROJECT="my-project"
SESSION_DIR="$HOME/.claude/projects/$PROJECT"

while true; do
  clear
  echo "=== Session Quality Dashboard ==="
  echo "Project: $PROJECT"
  echo "Last updated: $(date)"
  echo ""

  echo "Recent Sessions:"
  echo "--------------------------------"

  for session in $(ls -1t $SESSION_DIR | head -5); do
    SUCCESS=$(reveal claude://session/$session/tools --format json 2>/dev/null | \
      jq -r '.overall_success_rate // "N/A"')
    ERRORS=$(reveal claude://session/$session?errors --format json 2>/dev/null | \
      jq -r '.count // 0')

    printf "%-30s | Success: %5s%% | Errors: %2s\n" "$session" "$SUCCESS" "$ERRORS"
  done

  sleep 60
done
```

---

### 5. GitHub Actions Integration

```yaml
name: Session Quality Check

on:
  workflow_dispatch:
    inputs:
      session_name:
        description: 'Session name to analyze'
        required: true

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - name: Install reveal
        run: pip install reveal-tool

      - name: Analyze session
        id: analyze
        run: |
          SUCCESS_RATE=$(reveal claude://session/${{ inputs.session_name }}/tools --format json | \
            jq -r '.overall_success_rate')
          ERROR_COUNT=$(reveal claude://session/${{ inputs.session_name }}?errors --format json | \
            jq -r '.count // 0')

          echo "success_rate=$SUCCESS_RATE" >> $GITHUB_OUTPUT
          echo "error_count=$ERROR_COUNT" >> $GITHUB_OUTPUT

      - name: Check quality thresholds
        run: |
          if (( $(echo "${{ steps.analyze.outputs.success_rate }} < 80" | bc -l) )); then
            echo "::warning::Session success rate below 80%"
          fi

          if [ "${{ steps.analyze.outputs.error_count }}" -gt 5 ]; then
            echo "::error::Session has more than 5 errors"
            exit 1
          fi

      - name: Generate report
        run: |
          reveal claude://session/${{ inputs.session_name }}?summary > session-report.txt

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: session-report
          path: session-report.txt
```

---

### 6. Slack Alerting

```bash
#!/bin/bash
# slack-alert.sh - Alert on low session quality

SESSION="$1"
WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

SUCCESS_RATE=$(reveal claude://session/$SESSION/tools --format json | jq -r '.overall_success_rate')
ERROR_COUNT=$(reveal claude://session/$SESSION?errors --format json | jq -r '.count // 0')

if (( $(echo "$SUCCESS_RATE < 70" | bc -l) )) || [ "$ERROR_COUNT" -gt 10 ]; then
  MESSAGE="{
    \"text\": \"⚠️ Session Quality Alert: $SESSION\",
    \"attachments\": [{
      \"color\": \"warning\",
      \"fields\": [
        {\"title\": \"Success Rate\", \"value\": \"$SUCCESS_RATE%\", \"short\": true},
        {\"title\": \"Error Count\", \"value\": \"$ERROR_COUNT\", \"short\": true}
      ]
    }]
  }"

  curl -X POST -H 'Content-type: application/json' --data "$MESSAGE" $WEBHOOK_URL
fi
```

---

## Related Documentation

### Reveal Adapter Guides

- **[Domain Adapter Guide](DOMAIN_ADAPTER_GUIDE.md)** - Domain DNS and SSL inspection
- **[SSL Adapter Guide](SSL_ADAPTER_GUIDE.md)** - SSL/TLS certificate health monitoring
- **[Stats Adapter Guide](STATS_ADAPTER_GUIDE.md)** - Codebase metrics and quality analysis
- **[JSON Adapter Guide](JSON_ADAPTER_GUIDE.md)** - Navigate JSONL conversation files directly

### Reveal Core Documentation

- **[REVEAL_GUIDE.md](REVEAL_GUIDE.md)** - Complete reveal system guide
- **[PROGRESSIVE_DISCLOSURE.md](PROGRESSIVE_DISCLOSURE.md)** - Token-efficient patterns
- **[ADAPTER_OVERVIEW.md](ADAPTER_OVERVIEW.md)** - All adapters reference

---

## FAQ

### General Questions

**Q: What's the difference between claude:// and json://?**

A: **claude://** provides high-level conversation analysis (tool usage, errors, workflow). **json://** provides low-level JSONL navigation. Use claude:// for session analysis, json:// for raw data access.

---

**Q: Can I analyze a currently running session?**

A: No. claude:// only analyzes saved conversation files. Wait for the session to complete and save.

---

**Q: Where are conversation files stored?**

A: `~/.claude/projects/<project-dir>/<session-name>/conversation.jsonl`

---

**Q: How accurate are token estimates?**

A: Approximate (±10%). Formula: `tokens ≈ characters / 4`. Use for relative comparison, not absolute values.

---

**Q: Can I analyze multiple sessions at once?**

A: Not directly. Use shell loops for multi-session analysis. See [Integration Examples](#integration-examples).

---

### Tool Usage Questions

**Q: What does "success rate" mean?**

A: Percentage of tool calls that returned results without errors. Formula: `(Successful Calls / Total Calls) × 100`

---

**Q: What's a good tool success rate?**

A:
- **90-100%**: Excellent
- **75-89%**: Good
- **50-74%**: Fair (investigate patterns)
- **<50%**: Poor (review usage)

---

**Q: Why is my Bash success rate low?**

A: Common causes:
- Command syntax errors
- Environment issues (missing tools)
- Permission problems
- Incorrect paths

Review: `reveal claude://session/my-session?tools=Bash&errors`

---

**Q: Can I see specific tool parameters?**

A: Yes, use workflow: `reveal claude://session/my-session/workflow`

---

### File Operation Questions

**Q: What's a "hotspot" file?**

A: File with high access count (>5 reads). Indicates:
- Complex file structure
- Repeated exploration
- Missing information

**Action**: Consider summarizing or improving documentation.

---

**Q: How do I find files that were edited?**

A: `reveal claude://session/my-session/files --format json | jq '.files[] | select(.operations | contains(["Edit"]))'`

---

**Q: Can I see file diffs?**

A: No. claude:// tracks operations only, not content changes. Use git for diffs.

---

### Error Analysis Questions

**Q: How do I find why a session failed?**

A:
```bash
# Step 1: Check errors
reveal claude://session/failed-session?errors

# Step 2: View workflow to find failure point
reveal claude://session/failed-session/workflow

# Step 3: Review error context
reveal claude://session/failed-session/errors
```

---

**Q: What's "error context"?**

A: Surrounding messages before/after error (helps understand what led to error).

---

**Q: Can I filter errors by tool?**

A: Yes: `reveal claude://session/my-session?tools=Bash&errors`

---

### Token Optimization Questions

**Q: How do I reduce token usage?**

A: Analyze thinking blocks and file access:
```bash
reveal claude://session/my-session/thinking
reveal claude://session/my-session/files
```

Look for:
- Large thinking blocks (>500 tokens)
- Repeated file reads (same file multiple times)
- High file access counts (>5)

---

**Q: What's excessive thinking token usage?**

A: >30% of total session tokens. Indicates over-analysis or unclear prompts.

---

**Q: How do I find repeated file reads?**

A: `reveal claude://session/my-session/files` - Look for `access_count > 3`

---

### Query Parameter Questions

**Q: Can I combine query parameters?**

A: Yes:
```bash
reveal claude://session/my-session?tools=Bash&errors
reveal claude://session/my-session?role=user&contains=reveal
```

---

**Q: What's the difference between ?summary and /workflow?**

A:
- **?summary**: Comprehensive session summary with recommendations
- **/workflow**: Chronological tool operation sequence only

---

**Q: Can I search across all sessions?**

A: Not directly with claude://. Use shell loops:
```bash
for session in $(ls ~/.claude/projects/my-project/); do
  reveal claude://session/$session?contains=error
done
```

---

### Integration Questions

**Q: How do I integrate with monitoring tools?**

A: Use JSON output and parse with jq. See [Monitoring Dashboard](#4-monitoring-dashboard) example.

---

**Q: Can I export metrics to Prometheus?**

A: Yes, parse JSON output:
```bash
reveal claude://session/my-session/tools --format json | \
  jq -r '.tools[] | "session_tool_success_rate{session=\"my-session\",tool=\"\(.name)\"} \(.success_rate)"'
```

---

**Q: How do I automate session analysis in CI/CD?**

A: See [GitHub Actions Integration](#5-github-actions-integration) example.

---

---

**Last Updated**: 2026-02-14
**Adapter Version**: reveal 0.1.0+
**Documentation Version**: 1.0
