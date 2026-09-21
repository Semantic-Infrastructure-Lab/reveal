"""Simulate Windows' cp1252 default text encoding on any OS.

Any text-mode open() / Path.read_text() / write_text() that passes no encoding
gets cp1252, like Windows.  (PYTHONUTF8=0 LC_ALL=C gives ASCII on Linux, not
cp1252, so it is not a faithful stand-in.)  Stdout is untouched - set
PYTHONIOENCODING yourself.

    PYTHONUTF8=0 PYTHONPATH=scripts/cp1252_sim reveal check some.conf

Sanity check: a bare read_text() of a UTF-8 file containing '→' must print
mojibake ('â†’').  See internal-docs/design/ENCODING_ROBUSTNESS_2026-09-21.md.
"""
import builtins
import io

_real_open = builtins.open


def _open(file, mode='r', buffering=-1, encoding=None, errors=None, *a, **k):
    if encoding is None and 'b' not in mode and isinstance(file, (str, bytes)) or (
        encoding is None and 'b' not in mode and hasattr(file, '__fspath__')
    ):
        encoding = 'cp1252'
    return _real_open(file, mode, buffering, encoding, errors, *a, **k)


builtins.open = _open
io.open = _open
io.text_encoding = lambda encoding, stacklevel=2: 'cp1252' if encoding is None else encoding
