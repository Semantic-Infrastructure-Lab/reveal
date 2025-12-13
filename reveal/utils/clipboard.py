"""Clipboard utilities for reveal."""

import subprocess
import shutil


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard.

    Uses native clipboard utilities without external dependencies.
    Supports: xclip, xsel (Linux), pbcopy (macOS), clip (Windows), wl-copy (Wayland).

    Args:
        text: Text to copy to clipboard

    Returns:
        True if successful, False otherwise
    """
    # Try clipboard utilities in order of preference
    clipboard_cmds = [
        ['xclip', '-selection', 'clipboard'],  # Linux X11
        ['xsel', '--clipboard', '--input'],     # Linux X11 alternative
        ['wl-copy'],                             # Linux Wayland
        ['pbcopy'],                              # macOS
        ['clip'],                                # Windows
    ]

    for cmd in clipboard_cmds:
        if shutil.which(cmd[0]):
            try:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                process.communicate(input=text.encode('utf-8'))
                if process.returncode == 0:
                    return True
            except (subprocess.SubprocessError, OSError):
                continue

    return False
