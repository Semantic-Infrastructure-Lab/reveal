"""Windows rejects wildcard stat paths; lookup must enumerate the pattern instead."""
import errno
from pathlib import Path

from reveal.adapters.claude.markdown_lookup import MarkdownLookup


def test_recursive_prefix_does_not_stat_a_windows_wildcard(tmp_path, monkeypatch):
    nested = tmp_path / 'nested'
    nested.mkdir()
    target = nested / 'prefix.md'
    target.write_text('Qualified plan body', encoding='utf-8')
    original = Path.stat
    attempts = []
    def windows_stat(path, *args, **kwargs):
        if any(c in str(path) for c in '*?'):
            attempts.append(str(path))
            raise OSError(errno.EINVAL, 'Invalid argument')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', windows_stat)
    lookup = MarkdownLookup()
    selected = lookup.resolve(tmp_path, '**/pre')
    assert selected == target
    result = {}
    lookup.read(selected, result)
    assert result['content'] == 'Qualified plan body'
    assert lookup.discovery_errors == []
    assert not attempts
