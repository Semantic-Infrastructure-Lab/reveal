"""Resolve a call site to the one definition it reaches -- for the callee walk
(calls.index.walk_callees) that calls://?callees=X&depth=N answers from (and the retired
trace:// and ?root=).

A walk keyed by bare name merges every same-named function: two unrelated
`run()`s contribute each other's callees once either is reached. trace://
fixed that by walking definitions (BACK-1399); the recursive callees walk kept
the name-keyed BFS (BACK-1442). One walk now does both (BACK-2096) and resolves
each call site here: the caller's language family first (BACK-405), then what the
call is bound to -- a call whose qualifier or bare name an import binds reaches that
import's file, or no project definition when the import resolved to no file (BACK-2553,
BACK-2573) -- then a
same-file definition or the one its imports name, else the call is ambiguous and reported
as such, never guessed.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...analyzers.imports.bindings import ProjectBindings, at_module
from .index import _bare_callee_name, _lang_family

Definition = Dict[str, Any]


class CallResolver:
    """Resolves call-site text against a name -> [definition] index.

    Each definition is a dict with at least `file`, `line` and `family` (its file's language
    family, looked up once when the definitions were collected, BACK-2131); the index maps
    every lookup key (core.definition_names.lookup_keys) to its definitions.
    """

    def __init__(self, index: Dict[str, List[Definition]], directory: Optional[Path] = None) -> None:
        self.index = index
        self._bindings = ProjectBindings(directory)  # the directory the definitions were collected from
        self._alias_maps: Dict[str, Dict[str, str]] = {}
        self._families: Dict[str, str] = {}

    def resolve(self, call: str, caller_file: str) -> Tuple[str, Any]:
        """(bare name, target): target is one definition, a list of candidate
        definitions when the name stays ambiguous, or None when it reaches no project definition."""
        tail = _bare_callee_name(call)
        from ..ast.call_graph import build_alias_map
        if caller_file not in self._alias_maps:
            self._alias_maps[caller_file] = build_alias_map(caller_file)
        if '.' not in call:
            tail = self._alias_maps[caller_file].get(tail, tail)
        family = self._caller_family(caller_file)
        # A module is a call source (its top-level calls), never what a call reaches: Rust's
        # `mod parser;` is not the `parser(input)` a sibling calls (BACK-2569).
        candidates = [d for d in self.index.get(tail, [])
                      if (not family or d['family'] == family) and d.get('category') != 'modules']
        candidates = self._reachable(call, caller_file, candidates)
        if not candidates:
            return tail, None
        if len(candidates) == 1:
            return tail, candidates[0]
        return tail, self._disambiguate(call, tail, caller_file, candidates) or candidates

    def _reachable(self, call: str, caller_file: str, candidates: List[Definition]) -> List[Definition]:
        """The candidates the call can reach, given what its qualifier (``json`` of ``json.loads``)
        or bare name is bound to. Bound only by imports that resolved to no project file, it reaches
        none of them when they are outside the tree (BACK-2553), and when the verdict could not place
        them (``pytest``; a monorepo package root reveal does not model) only one whose file sits at
        the module's path (``dagster/_grpc/client.py`` for ``from dagster._grpc.client import f``,
        BACK-2573). A bare call to a name the file also defines reaches its own definition (it
        shadows the import)."""
        binding = self._bindings.of(caller_file).get(call.split('.')[0])
        if binding is None or not binding.unresolved:
            return candidates
        if '.' not in call and any(c['file'] == caller_file for c in candidates):
            return candidates
        return [c for c in candidates if at_module(c['file'], binding.modules)]

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
        via_import = self._via_import(call, tail, qualifier, caller_file, candidates)
        same_file = [c for c in candidates if c['file'] == caller_file]
        for group in ((via_import, same_file) if qualifier else (same_file, via_import)):
            if len(group) == 1:
                return group[0]
        return None

    def _via_import(self, call: str, tail: str, qualifier: str, caller_file: str,
                    candidates: List[Definition]) -> List[Definition]:
        """The candidates in the file the call's qualifier or bare name is imported from, narrowed to
        what the import names (BACK-2569). A module binds a name once: a bare name, or a namespace's
        member, is a module-level definition, never a class's method of that name (three.js
        DataUtils.js: `function toHalfFloat` and `static toHalfFloat`), and of several (TypeScript
        overload signatures, a Python redefinition) the last, the one the module ends up binding. A
        call through an imported class (`SnapCache.getReferenceSnapPoints`) is that class's member."""
        bindings = self._bindings.of(caller_file)
        binding = bindings.get(qualifier or (call if call in bindings else tail))
        imported = binding.target if binding else None
        if not imported:
            return []
        imported_path = Path(imported).resolve()
        via_import = [c for c in candidates if Path(c['file']).resolve() == imported_path]
        if len(via_import) < 2:
            return via_import
        if qualifier:
            owner = binding.origin.rsplit('.', 1)[-1] if binding.origin else qualifier
            owned = [c for c in via_import if c.get('owner') == owner]
            if owned:
                return owned[-1:]
        module_level = [c for c in via_import if not c.get('member')]
        return module_level[-1:] if module_level else via_import
