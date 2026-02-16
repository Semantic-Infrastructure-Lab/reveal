# claude:// Adapter Design Document

**Version:** 1.0.0
**Date:** 2026-01-18
**Status:** Design Document
**Author:** TIA (infernal-earth-0118)
**Session:** infernal-earth-0118

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Vision & Goals](#vision--goals)
3. [Problem Statement](#problem-statement)
4. [Architecture Overview](#architecture-overview)
5. [URI Syntax & Patterns](#uri-syntax--patterns)
6. [Implementation Specification](#implementation-specification)
7. [Progressive Disclosure Strategy](#progressive-disclosure-strategy)
8. [Quality Rules (C-Series)](#quality-rules-c-series)
9. [Integration with Reveal Ecosystem](#integration-with-reveal-ecosystem)
10. [TIA Session Domain Integration](#tia-session-domain-integration)
11. [Performance Targets](#performance-targets)
12. [Development Roadmap](#development-roadmap)
13. [Security & Privacy](#security--privacy)
14. [Testing Strategy](#testing-strategy)
15. [Documentation & Help](#documentation--help)

---

## Executive Summary

The `claude://` adapter brings Claude Code conversation analysis into reveal's progressive disclosure framework, enabling developers and AI agents to explore conversation history, tool usage, thinking patterns, and session artifacts with the same token-efficient patterns used across all reveal adapters.

**Core Value Propositions:**
- **Structure-first conversation exploration** (overview → messages → details)
- **Token optimization analysis** - Identify excessive thinking, repeated operations
- **Quality pattern detection** - Find anti-patterns (retry loops, file churn, circular deps)
- **Integration with TIA session domain** - Complement high-level session operations

**Implementation Strategy:**
- Pure Python implementation using stdlib (no external deps beyond reveal core)
- Leverage existing JSONL analyzer in reveal
- Ship as core adapter in reveal base install
- Phased rollout: basic queries (v0.40) → quality checks (v0.41) → cross-session (v0.42)

**Key Insight:** This adapter is reveal eating its own dogfood - using reveal to inspect Claude Code conversations that use reveal. Meta-circularity proves the framework's generality.

---

## Vision & Goals

### Primary Goals

1. **Enable conversation-aware semantic navigation** - Navigate Claude Code sessions with reveal's progressive disclosure
2. **Support post-session analysis** - Understand tool usage, token patterns, file operations
3. **Detect conversation anti-patterns** - Excessive retries, token bloat, circular operations
4. **Integrate with TIA workflow** - Orient → Navigate → Focus pattern for conversations

### Non-Goals (Out of Scope)

- ❌ Real-time conversation monitoring (use Claude Code's native UI)
- ❌ Conversation editing or replay
- ❌ Multi-agent conversation support (focus on Claude Code format)
- ❌ Alternative conversation formats (focus on Claude Code JSONL)

**Focus:** Read-only inspection, analysis, and quality checks on completed or in-progress Claude Code conversations.

---

## Problem Statement

### Current State: The Gap

**Existing Tools:**
1. **TIA `session` domain** - High-level session operations
   - `tia session read` → Summarized views (8+8 messages, noise filtered)
   - `tia session gron` → Schema exploration (flatten JSONL)
   - `tia session jq` → Precise queries (requires knowing exact paths)
   - **Gap:** No message-level semantic navigation, no progressive disclosure

2. **Reveal JSONL support** - Generic record navigation
   - `reveal conversation.jsonl --head 10` → First 10 records
   - `reveal conversation.jsonl 42` → Record #42
   - **Gap:** Not conversation-aware (no understanding of messages, tools, thinking)

### What's Missing

- **Progressive conversation navigation** (overview → thinking → tools → errors)
- **Conversation-specific filters** (user messages, assistant messages, tool calls)
- **Quality pattern detection** (retry loops, token bloat, file churn)
- **Analytics** (tool usage stats, token distribution, error analysis)

### User Scenarios

**Scenario 1: Post-session Review**
```bash
# Current workflow (fragmented):
tia session read session-name --full | less        # Overwhelming
tia session jq '.message.content[] | select(.type=="tool_use")' | wc -l  # Complex

# Desired workflow (progressive):
reveal claude://session/session-name              # Overview with stats
reveal claude://session/session-name/tools         # See all tool calls
reveal claude://session/session-name?tools=Bash    # Filter to Bash only
```

**Scenario 2: Debug Failed Session**
```bash
# Current: Manual inspection through 200+ messages
tia session read failed-build --full | grep -i error

# Desired: Structured error analysis
reveal claude://session/failed-build?errors        # All errors with context
reveal claude://session/failed-build/message/67    # Inspect specific failure
```

**Scenario 3: Token Optimization**
```bash
# Current: No visibility into token usage patterns
# Desired: Token analytics
reveal claude://session/heavy-session?summary      # Token distribution
reveal claude://session/heavy-session/thinking     # Extract thinking blocks
```

---

## Architecture Overview

### Component Structure

```
reveal/
├── adapters/
│   ├── claude/
│   │   ├── __init__.py          # Public API
│   │   ├── adapter.py           # ClaudeAdapter class
│   │   ├── conversation.py      # Conversation parser
│   │   ├── analytics.py         # Token/tool analytics
│   │   ├── filters.py           # Message filtering
│   │   └── help.py              # Help documentation
│   └── base.py                  # ResourceAdapter base
├── rules/
│   └── conversation/            # CQ-series: Conversation quality rules
│       ├── CQ001.py             # Excessive tool retries
│       ├── CQ002.py             # Token bloat (thinking >5k tokens)
│       ├── CQ003.py             # File churn (same file edited >10x)
│       ├── CQ004.py             # Circular operations
│       └── CQ005.py             # Missing session handoff
└── rendering/
    └── adapters/
        └── claude.py            # Claude-specific output formatting
```

### Integration Points

```
claude:// adapter
    ↓
├─ Uses reveal's JSONL analyzer → Parse conversation files
├─ Composes with json:// → json://conversation.jsonl/messages[42]
├─ Integrates with TIA session → Session discovery and mapping
└─ Uses reveal's core:
    ├─ ResourceAdapter protocol
    ├─ Output formatting (text, json, grep)
    └─ Quality rules framework (--check flag)
```

### Conversation File Format

Claude Code stores conversations in `~/.claude/projects/{project-dir}/{uuid}.jsonl`:

```json
{
  "type": "user|assistant|file-history-snapshot|tool_result",
  "message": {
    "role": "user|assistant",
    "content": [
      {"type": "text", "text": "..."},
      {"type": "thinking", "thinking": "..."},
      {"type": "tool_use", "name": "Bash", "input": {...}},
      {"type": "tool_result", "tool_use_id": "...", "content": "..."}
    ]
  },
  "uuid": "message-uuid",
  "timestamp": "2026-01-18T22:35:19.803Z",
  "cwd": "/working/directory",
  "sessionId": "session-uuid",
  "gitBranch": "master",
  "thinkingMetadata": {...},
  "todos": [...]
}
```

**Key Insights:**
- One JSONL record per turn (user or assistant)
- Assistant messages contain multiple content blocks (text, thinking, tools)
- Tool results are separate messages with type "tool_result"
- Timestamps enable temporal analysis

---

## URI Syntax & Patterns

### Session-Level Access

```bash
# Session overview
claude://session/{session-name}
# → Session metadata: message count, tools used, duration, errors

# All messages (paginated)
claude://session/{session-name}/messages
# → List of all messages with summaries

# Filtered message streams
claude://session/{session-name}/user           # User messages only
claude://session/{session-name}/assistant      # Assistant messages only
claude://session/{session-name}/thinking       # Thinking blocks only
claude://session/{session-name}/tools          # All tool calls
claude://session/{session-name}/files          # File operations (Read/Edit/Write)
```

### Message-Level Access

```bash
# Specific message by index
claude://session/{session-name}/message/42
# → Message #42 with full content and context

# Message range (progressive navigation)
claude://session/{session-name}/messages?range=40-50
# → Messages 40-50 (reveal's standard range syntax)

# First/last messages
claude://session/{session-name}/messages?head=10
claude://session/{session-name}/messages?tail=10
```

### Query Parameters

```bash
# Analytics and summaries
claude://session/{session-name}?summary
# → Token usage, tool stats, error count, duration

# Error detection
claude://session/{session-name}?errors
# → All tool failures, exceptions, error messages with context

# Tool filtering
claude://session/{session-name}?tools=Bash
claude://session/{session-name}?tools=Read
claude://session/{session-name}?tools=Edit
# → Filter to specific tool types

# Timeline view
claude://session/{session-name}?timeline
# → Chronological flow with durations

# Token analysis
claude://session/{session-name}?tokens
# → Token distribution by message, thinking block analysis
```

### Cross-Session Discovery

```bash
# Search all sessions
claude://sessions?search=fasthtml
# → Sessions mentioning "fasthtml"

# Recent sessions
claude://sessions?modified-after=7days
# → Sessions from last week

# Project-specific sessions
claude://sessions?project=reveal
# → Sessions working on reveal project

# Session comparison
claude://compare?session1=old-approach&session2=new-approach
# → Compare tool usage, token efficiency between sessions
```

### Composition Examples

```bash
# Combine with json:// for precise extraction
reveal json://$(reveal claude://session/current --format=path)/messages[42]

# Combine with grep for search
reveal claude://session/bugfix-session/tools --format=grep | grep -i "exit code"

# Combine with jq for analysis
reveal claude://session/current?summary --format=json | jq '.tools_used'
```

---

## Implementation Specification

### Phase 1: Core Adapter (v0.40)

**File:** `reveal/adapters/claude/adapter.py`

```python
from pathlib import Path
from typing import Dict, List, Any, Optional
from ..base import ResourceAdapter, register_adapter, register_renderer
import json
from collections import defaultdict

@register_adapter('claude')
class ClaudeAdapter(ResourceAdapter):
    """Adapter for Claude Code conversation analysis."""

    CONVERSATION_BASE = Path.home() / '.claude' / 'projects'

    def __init__(self, resource: str, query: str = None):
        self.resource = resource
        self.query = query
        self.session_name = self._parse_session_name(resource)
        self.conversation_path = self._find_conversation()
        self.messages = None  # Lazy load

    def _parse_session_name(self, resource: str) -> str:
        """Extract session name from URI."""
        # Handle: claude://session/infernal-earth-0118
        if resource.startswith('session/'):
            parts = resource.split('/')
            return parts[1] if len(parts) > 1 else None
        return resource

    def _find_conversation(self) -> Optional[Path]:
        """Find conversation JSONL file for session."""
        # Strategy 1: Check project directory for session
        session_dir = self.CONVERSATION_BASE / f"-home-scottsen-src-tia-sessions-{self.session_name}"
        if session_dir.exists():
            # Find .jsonl file (should be only one)
            jsonl_files = list(session_dir.glob('*.jsonl'))
            if jsonl_files:
                return jsonl_files[0]

        # Strategy 2: Search all project dirs
        for project_dir in self.CONVERSATION_BASE.iterdir():
            if self.session_name in project_dir.name:
                jsonl_files = list(project_dir.glob('*.jsonl'))
                if jsonl_files:
                    return jsonl_files[0]

        return None

    def _load_messages(self) -> List[Dict]:
        """Load and parse conversation JSONL."""
        if self.messages is not None:
            return self.messages

        if not self.conversation_path or not self.conversation_path.exists():
            raise FileNotFoundError(f"Conversation not found for session: {self.session_name}")

        messages = []
        with open(self.conversation_path, 'r') as f:
            for line in f:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # Skip malformed lines

        self.messages = messages
        return messages

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Return session structure based on query."""
        messages = self._load_messages()

        # Route based on resource path and query
        if self.query == 'summary':
            return self._get_summary(messages)
        elif self.query == 'errors':
            return self._get_errors(messages)
        elif self.query and self.query.startswith('tools='):
            tool_name = self.query.split('=')[1]
            return self._get_tool_calls(messages, tool_name)
        elif '/thinking' in self.resource:
            return self._get_thinking_blocks(messages)
        elif '/tools' in self.resource:
            return self._get_all_tools(messages)
        elif '/user' in self.resource:
            return self._filter_by_role(messages, 'user')
        elif '/assistant' in self.resource:
            return self._filter_by_role(messages, 'assistant')
        elif '/message/' in self.resource:
            msg_id = int(self.resource.split('/message/')[1])
            return self._get_message(messages, msg_id)
        else:
            return self._get_overview(messages)

    def _get_overview(self, messages: List[Dict]) -> Dict[str, Any]:
        """Session overview with key metrics."""
        tools_used = defaultdict(int)
        thinking_chars = 0
        user_messages = 0
        assistant_messages = 0
        errors = []
        file_operations = defaultdict(int)

        for msg in messages:
            msg_type = msg.get('type')

            if msg_type == 'user':
                user_messages += 1
            elif msg_type == 'assistant':
                assistant_messages += 1

                # Parse content blocks
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'tool_use':
                        tool_name = content.get('name')
                        tools_used[tool_name] += 1

                        # Track file operations
                        if tool_name in ('Read', 'Write', 'Edit'):
                            file_operations[tool_name] += 1

                    elif content.get('type') == 'thinking':
                        thinking_chars += len(content.get('thinking', ''))

        # Calculate duration
        timestamps = [msg.get('timestamp') for msg in messages if msg.get('timestamp')]
        duration = None
        if len(timestamps) >= 2:
            from datetime import datetime
            start = datetime.fromisoformat(timestamps[0].replace('Z', '+00:00'))
            end = datetime.fromisoformat(timestamps[-1].replace('Z', '+00:00'))
            duration = str(end - start)

        return {
            'contract_version': '1.0',
            'type': 'claude_session_overview',
            'source': str(self.conversation_path),
            'source_type': 'conversation',
            'session': self.session_name,
            'message_count': len(messages),
            'user_messages': user_messages,
            'assistant_messages': assistant_messages,
            'tools_used': dict(tools_used),
            'file_operations': dict(file_operations),
            'thinking_chars_approx': thinking_chars,
            'thinking_tokens_approx': thinking_chars // 4,  # Rough estimate
            'duration': duration,
            'conversation_file': str(self.conversation_path)
        }

    def _get_summary(self, messages: List[Dict]) -> Dict[str, Any]:
        """Detailed analytics summary."""
        overview = self._get_overview(messages)

        # Add detailed analytics
        tool_success_rate = self._calculate_tool_success_rate(messages)
        message_sizes = self._analyze_message_sizes(messages)

        overview.update({
            'tool_success_rate': tool_success_rate,
            'avg_message_size': message_sizes['avg'],
            'max_message_size': message_sizes['max'],
            'thinking_blocks': message_sizes['thinking_blocks']
        })

        return overview

    def _get_errors(self, messages: List[Dict]) -> Dict[str, Any]:
        """Extract all errors with context."""
        errors = []

        for i, msg in enumerate(messages):
            # Check tool results for errors
            if msg.get('type') == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'tool_result':
                        result_content = content.get('content', '')
                        if 'error' in result_content.lower() or 'failed' in result_content.lower():
                            errors.append({
                                'message_index': i,
                                'tool_use_id': content.get('tool_use_id'),
                                'content_preview': result_content[:200],
                                'timestamp': msg.get('timestamp')
                            })

        return {
            'contract_version': '1.0',
            'type': 'claude_errors',
            'source': str(self.conversation_path),
            'session': self.session_name,
            'error_count': len(errors),
            'errors': errors
        }

    def _get_tool_calls(self, messages: List[Dict], tool_name: str) -> Dict[str, Any]:
        """Extract all calls to specific tool."""
        tool_calls = []

        for i, msg in enumerate(messages):
            if msg.get('type') == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'tool_use' and content.get('name') == tool_name:
                        tool_calls.append({
                            'message_index': i,
                            'tool_use_id': content.get('id'),
                            'input': content.get('input'),
                            'timestamp': msg.get('timestamp')
                        })

        return {
            'contract_version': '1.0',
            'type': 'claude_tool_calls',
            'source': str(self.conversation_path),
            'session': self.session_name,
            'tool_name': tool_name,
            'call_count': len(tool_calls),
            'calls': tool_calls
        }

    def _get_thinking_blocks(self, messages: List[Dict]) -> Dict[str, Any]:
        """Extract all thinking blocks."""
        thinking_blocks = []

        for i, msg in enumerate(messages):
            if msg.get('type') == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'thinking':
                        thinking = content.get('thinking', '')
                        thinking_blocks.append({
                            'message_index': i,
                            'content': thinking,
                            'char_count': len(thinking),
                            'token_estimate': len(thinking) // 4,
                            'timestamp': msg.get('timestamp')
                        })

        return {
            'contract_version': '1.0',
            'type': 'claude_thinking',
            'source': str(self.conversation_path),
            'session': self.session_name,
            'thinking_block_count': len(thinking_blocks),
            'total_chars': sum(b['char_count'] for b in thinking_blocks),
            'total_tokens_estimate': sum(b['token_estimate'] for b in thinking_blocks),
            'blocks': thinking_blocks
        }

    # Helper methods
    def _calculate_tool_success_rate(self, messages: List[Dict]) -> Dict[str, float]:
        """Calculate success rate per tool."""
        # Implementation details...
        return {}

    def _analyze_message_sizes(self, messages: List[Dict]) -> Dict[str, Any]:
        """Analyze message size distribution."""
        # Implementation details...
        return {'avg': 0, 'max': 0, 'thinking_blocks': 0}

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for claude:// adapter."""
        return {
            'name': 'claude',
            'description': 'Navigate and analyze Claude Code conversations - progressive session exploration',
            'syntax': 'claude://session/{name}[/resource][?query]',
            'examples': [
                {
                    'uri': 'claude://session/infernal-earth-0118',
                    'description': 'Session overview (messages, tools, duration)'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/thinking',
                    'description': 'Extract all thinking blocks with token estimates'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118?tools=Bash',
                    'description': 'All Bash tool calls'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118?errors',
                    'description': 'Find errors and tool failures'
                },
                {
                    'uri': 'claude://sessions?search=reveal',
                    'description': 'Find sessions mentioning reveal'
                }
            ],
            'features': [
                'Progressive disclosure (overview → details → specifics)',
                'Tool usage analytics and filtering',
                'Token usage estimates and optimization insights',
                'Error detection with context',
                'Thinking block extraction and analysis',
                'File operation tracking'
            ],
            'workflows': [
                {
                    'name': 'Post-Session Review',
                    'scenario': 'Understand what happened in a completed session',
                    'steps': [
                        'reveal claude://session/session-name',
                        'reveal claude://session/session-name?summary',
                        'reveal claude://session/session-name/tools'
                    ]
                },
                {
                    'name': 'Debug Failed Session',
                    'scenario': 'Find why a session failed',
                    'steps': [
                        'reveal claude://session/failed-build?errors',
                        'reveal claude://session/failed-build/message/67',
                        'reveal claude://session/failed-build?tools=Bash'
                    ]
                },
                {
                    'name': 'Token Optimization',
                    'scenario': 'Identify token waste',
                    'steps': [
                        'reveal claude://session/current?summary',
                        'reveal claude://session/current/thinking',
                        'reveal claude://session/current?tools=Read'
                    ]
                }
            ],
            'try_now': [
                'reveal claude://session/$(basename $PWD)',
                'reveal claude://session/$(basename $PWD)?summary',
                'reveal claude://session/$(basename $PWD)/thinking'
            ],
            'notes': [
                'Conversation files stored in ~/.claude/projects/{project-dir}/',
                'Session names typically match directory names (e.g., infernal-earth-0118)',
                'Token estimates are approximate (chars / 4)',
                'Use --format=json for programmatic analysis with jq'
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal json:// - Navigate JSONL structure directly',
                'reveal help://adapters - All available adapters',
                'TIA session domain - High-level session operations'
            ]
        }
```

### Phase 2: Quality Rules (v0.41)

**File:** `reveal/rules/conversation/CQ001.py`

```python
from reveal.rules.base import BaseRule, Detection, RulePrefix, Severity

class CQ001(BaseRule):
    """Excessive tool call retries detected."""

    code = "CQ001"
    message = "Tool call retry pattern detected"
    category = RulePrefix.CQ  # Conversation Quality
    severity = Severity.MEDIUM

    def check(self, file_path, structure, content):
        if not file_path.startswith('claude://'):
            return []

        detections = []

        # Analyze tool call patterns
        tool_sequences = self._extract_tool_sequences(structure)

        for tool_name, calls in tool_sequences.items():
            # Check for repeated failures
            failure_streak = 0
            for call in calls:
                if self._is_failure(call):
                    failure_streak += 1
                else:
                    failure_streak = 0

                if failure_streak >= 5:
                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=call['message_index'],
                        message=f"Tool '{tool_name}' failed {failure_streak} times consecutively",
                        suggestion="Consider using a different approach or asking user for clarification",
                        context="Repeated tool failures indicate a misunderstanding of the problem or environment"
                    ))
                    failure_streak = 0  # Reset to avoid duplicate detections

        return detections

    def _extract_tool_sequences(self, structure):
        """Group tool calls by tool name."""
        # Implementation...
        return {}

    def _is_failure(self, call):
        """Determine if tool call failed."""
        # Check for error indicators in result
        return False
```

**Other CQ-series rules:**

- **CQ002:** Token bloat (thinking blocks >5000 tokens)
- **CQ003:** File churn (same file edited >10 times)
- **CQ004:** Circular operations (Read → Edit → Read same file repeatedly)
- **CQ005:** Missing session handoff (no README/save at end)
- **CQ006:** Excessive Read operations (>50 file reads in session)
- **CQ007:** Tool call imbalance (90% one tool type)

---

## Progressive Disclosure Strategy

Following reveal's core principle: **structure before content, overview before details**.

### Level 1: Session Overview (50-100 tokens)

```bash
reveal claude://session/infernal-earth-0118
```

**Output:**
```
Session: infernal-earth-0118
Duration: 45 minutes
Messages: 126 (63 user, 63 assistant)

Tools Used:
  Bash: 23 calls
  Read: 18 calls
  Write: 3 calls
  Edit: 2 calls

File Operations:
  Read: 18 files
  Write: 3 files
  Edit: 2 files

Thinking: ~8,500 tokens (estimated)
Errors: 2 tool failures

→ Next: reveal claude://session/infernal-earth-0118?summary
         reveal claude://session/infernal-earth-0118/tools
```

### Level 2: Analytics Summary (100-300 tokens)

```bash
reveal claude://session/infernal-earth-0118?summary
```

**Output:**
```
Session Analytics: infernal-earth-0118

Message Distribution:
  User:      63 messages (50%)
  Assistant: 63 messages (50%)
  Avg size:  1,200 chars/message

Tool Success Rate:
  Bash: 22/23 (95.7%)
  Read: 18/18 (100%)
  Write: 3/3 (100%)
  Edit: 2/2 (100%)

Token Usage (estimated):
  Total:    ~45,000 tokens
  Thinking: ~8,500 tokens (19%)
  Content:  ~36,500 tokens (81%)

Largest Thinking Block: Message #42 (1,200 tokens)

→ Next: reveal claude://session/infernal-earth-0118/thinking
         reveal claude://session/infernal-earth-0118?errors
```

### Level 3: Filtered Views (200-1000 tokens)

```bash
reveal claude://session/infernal-earth-0118/thinking
```

**Output:**
```
Thinking Blocks: infernal-earth-0118

Total: 15 blocks, ~8,500 tokens

Largest blocks:
  #42  1,200 tokens  "The user typed 'boot.' which means..."
  #67  1,050 tokens  "I need to analyze the conversation structure..."
  #89    890 tokens  "Let me consider how the claude:// adapter..."

Distribution:
  <500 tokens:   8 blocks (53%)
  500-1000:      4 blocks (27%)
  1000-2000:     3 blocks (20%)
  >2000 tokens:  0 blocks (0%)

→ Next: reveal claude://session/infernal-earth-0118/message/42
```

### Level 4: Specific Messages (full content)

```bash
reveal claude://session/infernal-earth-0118/message/42
```

**Output:**
```
Message #42 - Assistant (2026-01-18 22:35:25)

Thinking (1,200 tokens):
  "The user typed 'boot.' which means I need to follow the boot procedure:

  1. Run `tia-boot` (do NOT run reveal --agent-help)
  2. Check status: ⚠️/FAILED → acknowledge, offer fix
  ..."

Tool Calls:
  1. Bash: tia-boot
  2. Bash: tia session --help
  3. Bash: reveal --help

Message content: [Text response about boot sequence...]

→ Next: reveal claude://session/infernal-earth-0118/message/43
```

---

## Quality Rules (CQ-Series)

### Rule Categories

**CQ-series:** Conversation quality and anti-patterns

### Implemented Rules

#### CQ001: Excessive Tool Retries
**Problem:** Same tool failing repeatedly (>5 consecutive failures)
**Detection:** Sequence analysis of tool results
**Severity:** MEDIUM
**Fix:** Consider alternative approach or ask user

#### CQ002: Token Bloat
**Problem:** Thinking blocks >5000 tokens
**Detection:** Analyze thinking block sizes
**Severity:** LOW (informational)
**Fix:** Review reasoning complexity, consider splitting problem

#### CQ003: File Churn
**Problem:** Same file edited >10 times in session
**Detection:** Track file paths in Edit/Write operations
**Severity:** MEDIUM
**Fix:** Plan changes before editing, use Read → plan → Edit pattern

#### CQ004: Circular Operations
**Problem:** Read → Edit → Read same file repeatedly
**Detection:** Pattern matching in file operation sequences
**Severity:** MEDIUM
**Fix:** Load file once, make multiple changes, verify once

#### CQ005: Missing Handoff
**Problem:** Session ends without save/README
**Detection:** Check last 5 messages for save commands or README creation
**Severity:** HIGH
**Fix:** Always save session state before ending

#### CQ006: Read Overload
**Problem:** >50 Read operations in single session
**Detection:** Count Read tool calls
**Severity:** LOW
**Fix:** Use Explore agent or progressive disclosure patterns

#### CQ007: Tool Imbalance
**Problem:** >90% of tool calls are single tool type
**Detection:** Calculate tool usage distribution
**Severity:** LOW (informational)
**Fix:** Consider if using most efficient tool for each task

---

## Integration with Reveal Ecosystem

### Composition with Existing Adapters

```bash
# Combine with json:// for precise queries
reveal json://~/.claude/projects/session-dir/uuid.jsonl/messages[42]

# Combine with diff:// to compare sessions
reveal diff://claude:session/v1 vs claude:session/v2

# Combine with ast:// to analyze generated code
# (Extract code from session, then analyze)
reveal claude://session/current/files | grep "\.py$" | xargs reveal --check
```

### Integration with TIA Session Domain

**Division of Responsibilities:**

| Task | Tool | Why |
|------|------|-----|
| Session discovery | `tia session overview` | High-level portfolio view |
| Session search | `tia session search` | Keyword/semantic search across sessions |
| Session context loading | `tia session context` | Quick handoff for continuation |
| Session saving | `tia session save` | Create README, archive state |
| **Message-level navigation** | `reveal claude://` | Progressive disclosure of messages |
| **Tool analytics** | `reveal claude://` | Detailed tool usage patterns |
| **Quality checks** | `reveal claude:// --check` | Conversation anti-patterns |
| **Token analysis** | `reveal claude://` | Token distribution and optimization |

**Workflow Integration:**

```bash
# ORIENT: Session landscape (TIA)
tia session overview

# NAVIGATE: Find session (TIA)
tia session recent | grep 'reveal'

# FOCUS: Explore conversation (Reveal)
reveal claude://session/epic-isotope-0116
reveal claude://session/epic-isotope-0116/thinking
reveal claude://session/epic-isotope-0116?tools=Bash

# ANALYZE: Quality check (Reveal)
reveal claude://session/epic-isotope-0116 --check

# OPTIMIZE: Compare approaches (Reveal)
reveal claude://session/old-way?summary
reveal claude://session/new-way?summary
```

---

## TIA Session Domain Integration

### Session Name Resolution

**Challenge:** Map session names to conversation file paths

**Solution:** Leverage TIA's existing session discovery

```python
class ClaudeAdapter:
    def _find_conversation(self) -> Optional[Path]:
        """Find conversation JSONL for session."""

        # Strategy 1: Direct lookup via TIA
        # (if TIA is available and session exists in TIA index)
        tia_sessions_dir = Path.home() / 'src' / 'tia' / 'sessions'
        if (tia_sessions_dir / self.session_name).exists():
            # Session exists in TIA, look for corresponding conversation
            project_dir = self.CONVERSATION_BASE / f"-home-scottsen-src-tia-sessions-{self.session_name}"
            if project_dir.exists():
                jsonl_files = list(project_dir.glob('*.jsonl'))
                if jsonl_files:
                    return jsonl_files[0]

        # Strategy 2: Fuzzy search across all project dirs
        # (for sessions outside TIA or renamed)
        for project_dir in self.CONVERSATION_BASE.iterdir():
            if self.session_name in project_dir.name:
                jsonl_files = list(project_dir.glob('*.jsonl'))
                if jsonl_files:
                    return jsonl_files[0]

        return None
```

### Current Session Detection

```python
def _get_current_session() -> Optional[str]:
    """Detect current session name from CWD."""
    cwd = Path.cwd()

    # Check if we're in a TIA session directory
    if 'sessions' in cwd.parts:
        # Extract session name (directory name)
        return cwd.name

    return None
```

**Usage:**
```bash
# From within session directory
cd ~/src/tia/sessions/infernal-earth-0118
reveal claude://session/current   # Auto-detects session name
```

---

## Performance Targets

### Parsing Performance

- **Conversation loading:** <100ms for 500 messages
- **Overview generation:** <50ms
- **Filter operations:** <100ms for 1000 messages
- **Quality checks:** <500ms for full session

### Memory Efficiency

- **Lazy loading:** Don't parse entire conversation upfront
- **Streaming:** Process messages incrementally for large sessions
- **Caching:** Cache parsed structure for repeated queries

### Optimization Strategies

1. **Lazy message loading:** Only parse when needed
2. **Index generation:** Cache message index on first access
3. **Incremental parsing:** Stream JSONL line-by-line
4. **Query planning:** Optimize filter operations

---

## Development Roadmap

### Phase 1: Core Adapter (v0.40) - 8-12 hours

**Goal:** Basic conversation navigation and overview

**Deliverables:**
- [ ] `reveal/adapters/claude/adapter.py` - Core adapter implementation
- [ ] Session overview (`claude://session/{name}`)
- [ ] Message filtering (`/user`, `/assistant`, `/thinking`, `/tools`)
- [ ] Basic help documentation
- [ ] Integration tests (20 tests)
- [ ] Documentation: `CLAUDE_ADAPTER_GUIDE.md`

**Timeline:** 2 days

### Phase 2: Analytics & Queries (v0.41) - 6-10 hours

**Goal:** Deep analytics and query support

**Deliverables:**
- [ ] Query support (`?summary`, `?errors`, `?tools=X`)
- [ ] Token usage analytics
- [ ] Tool success rate calculation
- [ ] Error extraction with context
- [ ] Timeline reconstruction
- [ ] 15 additional tests

**Timeline:** 1-2 days

### Phase 3: Quality Rules (v0.41) - 8-12 hours

**Goal:** Conversation anti-pattern detection

**Deliverables:**
- [ ] CQ001: Excessive retries
- [ ] CQ002: Token bloat
- [ ] CQ003: File churn
- [ ] CQ004: Circular operations
- [ ] CQ005: Missing handoff
- [ ] CQ006: Read overload
- [ ] CQ007: Tool imbalance
- [ ] 30 rule tests

**Timeline:** 2 days

### Phase 4: Cross-Session (v0.42) - 6-8 hours

**Goal:** Multi-session analysis and comparison

**Deliverables:**
- [ ] `claude://sessions?search=term` - Session discovery
- [ ] Session comparison (`claude://compare?...`)
- [ ] Pattern analysis across sessions
- [ ] Efficiency benchmarking
- [ ] 15 additional tests

**Timeline:** 1 day

### Phase 5: Polish & Launch (v0.43) - 4-6 hours

**Goal:** Production-ready release

**Deliverables:**
- [ ] Comprehensive adapter guide
- [ ] Integration with TIA docs
- [ ] Performance optimization
- [ ] Edge case handling
- [ ] Release blog post

**Timeline:** 1 day

**Total Effort:** 32-48 hours (5-7 working days)

---

## Security & Privacy

### Conversation Data Sensitivity

**Concerns:**
1. Conversations may contain sensitive data (credentials, API keys, personal info)
2. File paths may reveal private directory structures
3. Error messages may leak system information

### Mitigation Strategies

#### 1. Redaction Rules

```python
class ClaudeAdapter:
    SENSITIVE_PATTERNS = [
        r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
        r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
        r'token["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
        r'secret["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
    ]

    def _redact_sensitive(self, content: str) -> str:
        """Redact sensitive values from content."""
        for pattern in self.SENSITIVE_PATTERNS:
            content = re.sub(pattern, r'\1***', content)
        return content
```

#### 2. Path Sanitization

```python
def _sanitize_paths(self, structure: Dict) -> Dict:
    """Replace full paths with relative or sanitized versions."""
    # Replace /home/user/... with ~/...
    # Replace absolute paths with project-relative
    return structure
```

#### 3. Opt-in Detailed Mode

```bash
# Default: Redacted
reveal claude://session/current

# Explicit: Full content (use carefully)
reveal claude://session/current --no-redact
```

#### 4. Respect .gitignore

Don't include conversations for sessions working in directories that would be .gitignore'd

### Privacy Best Practices

**Documentation warnings:**
- "⚠️ Conversations may contain sensitive data. Review output before sharing."
- "Use --no-redact only in secure environments"
- "Consider environment variables (reveal env://) for secrets, not hardcoded values"

---

## Testing Strategy

### Unit Tests (60 tests)

**File:** `tests/adapters/test_claude_adapter.py`

```python
def test_session_overview():
    """Test basic session overview generation."""
    adapter = ClaudeAdapter('session/test-session')
    overview = adapter.get_structure()

    assert overview['message_count'] > 0
    assert 'tools_used' in overview
    assert 'duration' in overview

def test_thinking_extraction():
    """Test thinking block extraction."""
    adapter = ClaudeAdapter('session/test-session/thinking')
    result = adapter.get_structure()

    assert result['type'] == 'claude_thinking'
    assert result['thinking_block_count'] >= 0
    assert 'blocks' in result

def test_error_detection():
    """Test error extraction."""
    adapter = ClaudeAdapter('session/test-session', query='errors')
    errors = adapter.get_structure()

    assert 'error_count' in errors
    assert 'errors' in errors

def test_tool_filtering():
    """Test tool-specific filtering."""
    adapter = ClaudeAdapter('session/test-session', query='tools=Bash')
    result = adapter.get_structure()

    assert result['tool_name'] == 'Bash'
    assert 'call_count' in result
```

### Integration Tests (20 tests)

```python
def test_real_session_analysis():
    """Test on actual conversation file."""
    # Use fixture conversation file
    result = subprocess.run(
        ['reveal', 'claude://session/fixture-session'],
        capture_output=True
    )
    assert result.returncode == 0
    assert b'Session:' in result.stdout

def test_quality_checks():
    """Test conversation quality rules."""
    result = subprocess.run(
        ['reveal', 'claude://session/fixture-session', '--check'],
        capture_output=True
    )
    assert result.returncode == 0
```

### Test Fixtures

**File:** `tests/fixtures/conversations/test-session.jsonl`

Create synthetic conversation files representing common scenarios:
- Normal session (happy path)
- Session with errors
- Session with excessive retries
- Token-heavy session
- File-churn session

---

## Documentation & Help

### Help System Integration

**File:** `reveal/adapters/claude/help.py`

```python
STATIC_HELP = {
    'claude': 'adapters/CLAUDE_ADAPTER_GUIDE.md',
    'claude-workflows': 'adapters/CLAUDE_ADAPTER_WORKFLOWS.md',
}
```

**Access:**
```bash
reveal help://claude           # Inline help (from get_help())
reveal help://claude-guide     # Comprehensive guide
reveal help://claude-workflows # Common workflows
```

### Comprehensive Guide

**File:** `reveal/docs/CLAUDE_ADAPTER_GUIDE.md`

Sections:
1. Quick Start (copy-paste examples)
2. URI Syntax Reference
3. Progressive Disclosure Pattern
4. Common Workflows
5. Quality Rules Explanation
6. Integration with TIA
7. Performance Tips
8. Troubleshooting

### Examples Section

```markdown
## Examples

### Post-Session Review
```bash
# Step 1: Overview
$ reveal claude://session/epic-isotope-0116
Session: epic-isotope-0116
Duration: 2h 15m
Messages: 234 (117 user, 117 assistant)
Tools: Bash (45), Read (32), Write (8), Edit (5)
Errors: 3

# Step 2: Check for issues
$ reveal claude://session/epic-isotope-0116 --check
CQ001: Bash tool failed 6 times consecutively (messages 45-50)
CQ003: File 'config.py' edited 12 times (high churn)

# Step 3: Investigate
$ reveal claude://session/epic-isotope-0116?errors
Error #1: Message 45 - Bash: command not found
Error #2: Message 47 - Bash: permission denied
...
```
```

---

## Open Questions & Decisions

### 1. Session Name Resolution

**Question:** How to handle session names that don't match directory names?

**Options:**
A. Require exact match (strict)
B. Fuzzy matching (user-friendly but slower)
C. Explicit mapping file

**Decision:** Start with fuzzy matching (Option B), add explicit mapping in Phase 4 if needed

### 2. Performance vs. Features

**Question:** Should we parse entire conversation upfront or use lazy loading?

**Options:**
A. Parse all (simpler code, higher memory)
B. Lazy load (complex code, better performance)

**Decision:** Lazy loading for Phase 1, optimize in Phase 2 based on real usage

### 3. Output Verbosity

**Question:** How much detail in default output?

**Options:**
A. Minimal (50 tokens, breadcrumbs to more)
B. Moderate (200 tokens, balanced)
C. Detailed (500+ tokens, comprehensive)

**Decision:** Follow reveal pattern - Minimal (Option A) with clear breadcrumbs

### 4. Cross-Session Storage

**Question:** Should we build an index for fast cross-session search?

**Options:**
A. No index (scan on demand, slower but simpler)
B. Sqlite index (fast, adds complexity)
C. JSON cache (middle ground)

**Decision:** No index for Phase 1-3, evaluate in Phase 4 based on performance

---

## Success Metrics

### Adoption Metrics

- **Usage:** 10+ developers use claude:// in first month
- **Integration:** TIA documentation references claude:// adapter
- **Feedback:** Positive responses on utility and token efficiency

### Technical Metrics

- **Performance:** <100ms for overview generation
- **Coverage:** 80% test coverage
- **Quality:** C-series rules detect >5 anti-patterns in test sessions

### Impact Metrics

- **Token savings:** 10x reduction vs `tia session read --full | grep`
- **Time savings:** 5x faster to find specific information in sessions
- **Insights:** Users discover patterns they wouldn't have found manually

---

## Appendix A: Conversation File Schema

Full schema documentation for Claude Code JSONL format:

```typescript
interface ConversationRecord {
  // Message type
  type: 'user' | 'assistant' | 'file-history-snapshot' | 'tool_result';

  // Message content (for user/assistant)
  message?: {
    role: 'user' | 'assistant';
    content: ContentBlock[];
  };

  // Metadata
  uuid: string;
  timestamp: string; // ISO 8601
  sessionId: string;
  cwd: string;
  gitBranch?: string;

  // Thinking metadata (assistant only)
  thinkingMetadata?: {
    level: 'high' | 'medium' | 'low';
    disabled: boolean;
    triggers: string[];
  };

  // Todo tracking
  todos?: TodoItem[];

  // Continuation
  parentUuid?: string | null;
  isSidechain: boolean;
  userType?: 'external';
  version?: string;
}

interface ContentBlock {
  type: 'text' | 'thinking' | 'tool_use' | 'tool_result';

  // Text content
  text?: string;

  // Thinking content
  thinking?: string;
  signature?: string; // Cryptographic signature

  // Tool use
  name?: string;
  id?: string;
  input?: Record<string, any>;

  // Tool result
  tool_use_id?: string;
  content?: string;
  is_error?: boolean;
}

interface TodoItem {
  content: string;
  activeForm: string;
  status: 'pending' | 'in_progress' | 'completed';
}
```

---

## Appendix B: Related Work

### Existing Tools

- **TIA session domain:** High-level session operations
- **jq:** JSON querying (complex syntax, not conversation-aware)
- **gron:** JSON flattening (useful but verbose)
- **reveal json://:** Generic JSON navigation

### Why claude:// is Different

1. **Conversation-aware:** Understands message structure, roles, tools
2. **Progressive disclosure:** Overview → details → specifics
3. **Quality checks:** Detect anti-patterns automatically
4. **Integration:** Works with TIA and reveal ecosystems
5. **Token-optimized:** Output designed for AI agent consumption

---

## Appendix C: Implementation Checklist

### Pre-Development

- [ ] Review this design doc with stakeholders
- [ ] Confirm integration points with TIA
- [ ] Set up test fixtures
- [ ] Create GitHub issues/milestones

### Phase 1: Core Adapter

- [ ] Create `reveal/adapters/claude/` directory structure
- [ ] Implement `ClaudeAdapter` base class
- [ ] Session discovery and conversation loading
- [ ] Overview generation
- [ ] Message filtering (user/assistant/thinking/tools)
- [ ] Help documentation (`get_help()`)
- [ ] Unit tests (20 tests)
- [ ] Integration tests (5 tests)
- [ ] Update reveal docs

### Phase 2: Analytics

- [ ] Implement query handlers (`?summary`, `?errors`, `?tools=X`)
- [ ] Token usage analytics
- [ ] Tool success rate calculation
- [ ] Error extraction
- [ ] Timeline reconstruction
- [ ] Unit tests (15 tests)
- [ ] Update guide with examples

### Phase 3: Quality Rules

- [ ] Implement CQ001-CQ007 rules
- [ ] Rule tests (30 tests)
- [ ] Document each rule
- [ ] Add troubleshooting guide

### Phase 4: Cross-Session

- [ ] Session search (`claude://sessions?search=...`)
- [ ] Session comparison
- [ ] Pattern analysis
- [ ] Unit tests (15 tests)
- [ ] Performance benchmarks

### Phase 5: Launch

- [ ] Comprehensive guide
- [ ] Release notes
- [ ] Blog post
- [ ] Update TIA docs
- [ ] User feedback collection

---

**End of Design Document**

---

**Next Steps:**

1. Review and refine this design document
2. Get feedback from TIA maintainers
3. Create GitHub issues for each phase
4. Begin Phase 1 implementation in a dedicated session
5. Iterate based on real usage and feedback

**Session Handoff:**

This design document is ready for implementation. The next session should:
1. Create the basic adapter structure
2. Implement session overview functionality
3. Write initial tests
4. Validate against real conversation files

**Estimated Total Effort:** 5-7 working days for complete implementation (Phases 1-5)
