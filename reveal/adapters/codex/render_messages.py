"""Message turn renderers for the Codex adapter."""


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
