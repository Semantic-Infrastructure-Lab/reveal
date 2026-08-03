"""Message turn renderers for the Codex adapter."""

import json


def _render_codex_messages(result: dict) -> None:
    messages = result.get('messages', [])
    total = result.get('total_turns', len(messages))
    print(f"Codex Messages: {total} turn(s)")
    print()
    for msg in messages:
        role = msg.get('role', '?').upper()
        ts = (msg.get('timestamp') or '')[:19]
        phase = msg.get('phase')
        header = f"[{role}]" + (f" phase={phase}" if phase else '') + (f"  {ts}" if ts else '')
        print(header)
        text = msg.get('message', '')
        if text:
            for line in str(text).splitlines():
                print(f"  {line}")
        print()


def _render_codex_digest(result: dict) -> None:
    """Render the composed overview + prompts + agent-narrative digest (BACK-943)."""
    session_id = result.get('session_id', 'unknown')
    title = result.get('title')

    if 'error' in result:
        print(f"Error: {result['error']}")
        return

    print(f"Digest: {session_id}" + (f" — {title}" if title else ''))
    dur = result.get('duration_ms')
    dur_str = f"{dur/1000:.1f}s" if dur is not None else '?'
    print(f"Model: {result.get('model', '?')}  |  Duration: {dur_str}  |  "
          f"{result.get('user_turns', 0)} user / {result.get('agent_turns', 0)} agent turns")
    print()

    print(f"--- Prompts ({result.get('prompt_count', 0)}) ---")
    for turn in result.get('prompts', []):
        ts = (turn.get('timestamp') or '')[:19].replace('T', ' ')
        text = (turn.get('message') or '').strip()
        print(f"[{ts}]")
        if len(text) > 500:
            print(text[:500])
            print(f"  ... ({len(text) - 500} more chars)")
        else:
            print(text)
        print()

    print(f"--- Assistant narrative ({result.get('narrative_turn_count', 0)} turns) ---")
    for turn in result.get('assistant_narrative', []):
        ts = (turn.get('timestamp') or '')[:19].replace('T', ' ')
        text = (turn.get('message') or '').strip()
        print(f"[{ts}]")
        if len(text) > 500:
            print(text[:500])
            print(f"  ... ({len(text) - 500} more chars)")
        else:
            print(text)
        print()


def _render_codex_exchanges(result: dict) -> None:
    """Render prompt -> next-reply pairs (BACK-943)."""
    session_id = result.get('session_id', 'unknown')
    count = result.get('exchange_count', 0)

    if 'error' in result:
        print(f"Error: {result['error']}")
        return

    print(f"Exchanges: {session_id} ({count} total)")
    print()

    for ex in result.get('exchanges', []):
        ts = (ex.get('prompt_timestamp') or '')[:19].replace('T', ' ')
        prompt = (ex.get('prompt') or '').strip()
        print(f"[{ts}]")
        print(f"Q: {prompt[:300]}{'...' if len(prompt) > 300 else ''}")

        answer = ex.get('answer')
        if answer is None:
            print("A: [no agent reply found before the next prompt]")
        else:
            if len(answer) > 600:
                print(f"A: {answer[:600]}")
                print(f"  ... ({len(answer) - 600} more chars)")
            else:
                print(f"A: {answer}")
        print()


def _render_codex_message(result: dict) -> None:
    """Render a single raw JSONL record by index (BACK-943)."""
    session_id = result.get('session_id', 'unknown')

    if 'error' in result:
        print(f"Error: {result['error']}")
        return

    idx = result.get('record_index', '?')
    ts = (result.get('timestamp') or '')[:19].replace('T', ' ')
    print(f"Record {idx}: {session_id}")
    print(f"Type: {result.get('record_type', '?')}/{result.get('payload_type', '?')}  |  {ts}")
    print()
    print(json.dumps(result.get('record', {}), indent=2, ensure_ascii=False, default=str))
