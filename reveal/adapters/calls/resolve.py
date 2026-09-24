"""Resolve a call site to the one definition it reaches -- shared by trace://
and calls://?callees=X&depth=N.

A walk keyed by bare name merges every same-named function: two unrelated
`run()`s contribute each other's callees once either is reached. trace://
fixed that by walking definitions (BACK-1399); the recursive callees walk kept
the name-keyed BFS (BACK-1442). Both now resolve each call site here: the
caller's language family first (BACK-405), then a same-file definition or the
one its imports name, else the call is ambiguous and reported as such, never
guessed.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .index import _bare_callee_name, _lang_family

Definition = Dict[str, Any]


class CallResolver:
    """Resolves call-site text against a name -> [definition] index.

    Each definition is a dict with at least `file` and `line`; the index maps
    every lookup key (core.definition_names.lookup_keys) to its definitions.
    """

    def __init__(self, index: Dict[str, List[Definition]]) -> None:
        self.index = index
        self._symbol_maps: Dict[str, Dict[str, Optional[str]]] = {}

    def resolve(self, call: str, caller_file: str) -> Tuple[str, Any]:
        """(bare name, target): target is one definition, a list of candidate
        definitions when the name stays ambiguous, or None when external."""
        tail = _bare_callee_name(call)
        family = _lang_family(caller_file)
        candidates = [d for d in self.index.get(tail, [])
                      if not family or _lang_family(d['file']) == family]
        if not candidates:
            return tail, None
        if len(candidates) == 1:
            return tail, candidates[0]
        return tail, self._disambiguate(call, tail, caller_file, candidates) or candidates

    def _disambiguate(self, call: str, tail: str, caller_file: str,
                      candidates: List[Definition]) -> Optional[Definition]:
        """The one candidate the caller's own file or its imports point at.
        A bare call prefers a same-file definition (it shadows imports); a
        qualified one (`strings.rtrim`, `h.run`) prefers the module it names."""
        qualifier = call.split('.')[0] if '.' in call else ''
        imported = self._symbol_map(caller_file).get(qualifier or tail)
        imported_path = Path(imported).resolve() if imported else None
        via_import = [c for c in candidates if imported_path and Path(c['file']).resolve() == imported_path]
        same_file = [c for c in candidates if c['file'] == caller_file]
        for group in ((via_import, same_file) if qualifier else (same_file, via_import)):
            if len(group) == 1:
                return group[0]
        return None

    def _symbol_map(self, file_path: str) -> Dict[str, Optional[str]]:
        if file_path not in self._symbol_maps:
            from ..ast.call_graph import build_symbol_map
            self._symbol_maps[file_path] = build_symbol_map(file_path)
        return self._symbol_maps[file_path]
