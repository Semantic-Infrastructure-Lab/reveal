"""Resolve a call site to the one definition it reaches -- for the callee walk
(calls.index.walk_callees) that calls://?callees=X&depth=N answers from (and the retired
trace:// and ?root=).

A walk keyed by bare name merges every same-named function: two unrelated
`run()`s contribute each other's callees once either is reached. trace://
fixed that by walking definitions (BACK-1399); the recursive callees walk kept
the name-keyed BFS (BACK-1442). One walk now does both (BACK-2096) and resolves
each call site here: the caller's language family first (BACK-405), then a
same-file definition or the one its imports name, else the call is ambiguous
and reported as such, never guessed.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .index import _bare_callee_name, _lang_family

Definition = Dict[str, Any]


class CallResolver:
    """Resolves call-site text against a name -> [definition] index.

    Each definition is a dict with at least `file`, `line` and `family` (its file's language
    family, looked up once when the definitions were collected, BACK-2131); the index maps
    every lookup key (core.definition_names.lookup_keys) to its definitions.
    """

    def __init__(self, index: Dict[str, List[Definition]]) -> None:
        self.index = index
        self._alias_maps: Dict[str, Dict[str, str]] = {}
        self._symbol_maps: Dict[str, Dict[str, Optional[str]]] = {}
        self._families: Dict[str, str] = {}

    def resolve(self, call: str, caller_file: str) -> Tuple[str, Any]:
        """(bare name, target): target is one definition, a list of candidate
        definitions when the name stays ambiguous, or None when external."""
        tail = _bare_callee_name(call)
        from ..ast.call_graph import build_alias_map
        if caller_file not in self._alias_maps:
            self._alias_maps[caller_file] = build_alias_map(caller_file)
        if '.' not in call:
            tail = self._alias_maps[caller_file].get(tail, tail)
        family = self._caller_family(caller_file)
        candidates = [d for d in self.index.get(tail, [])
                      if not family or d['family'] == family]
        if not candidates:
            return tail, None
        if len(candidates) == 1:
            return tail, candidates[0]
        return tail, self._disambiguate(call, tail, caller_file, candidates) or candidates

    def _caller_family(self, caller_file: str) -> str:
        if caller_file not in self._families:
            self._families[caller_file] = _lang_family(caller_file)
        return self._families[caller_file]

    def _disambiguate(self, call: str, tail: str, caller_file: str,
                      candidates: List[Definition]) -> Optional[Definition]:
        """The one candidate the caller's own file or its imports point at.
        A bare call prefers a same-file definition (it shadows imports); a
        qualified one (`strings.rtrim`, `h.run`) prefers the module it names."""
        qualifier = call.split('.')[0] if '.' in call else ''
        symbols = self._symbol_map(caller_file)
        imported = symbols.get(qualifier or (call if call in symbols else tail))
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
