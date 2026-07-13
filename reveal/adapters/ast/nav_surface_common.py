"""Shared tree-sitter nav helpers (BACK-570).

Three helpers were copy-pasted byte-for-byte across every per-language
``nav_surface_<lang>.py`` scanner (and ``nav_contracts_ruby.py``): a UTF-8
node-text slice, a 1-based line number, and a dedup-on-``(name, file, line)``
list append. Consolidated here so a change to the dedup key or the
tree-sitter node API lands in one place instead of eight.
"""

from typing import Any, Dict, List


def _get_text(node, content_bytes: bytes) -> str:
    return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')


def _get_line(node) -> int:
    return node.start_position().row + 1


def _add_once(lst: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    key = (entry.get('name', ''), entry.get('file', ''), entry.get('line', 0))
    for existing in lst:
        if (existing.get('name', ''), existing.get('file', ''), existing.get('line', 0)) == key:
            return
    lst.append(entry)
