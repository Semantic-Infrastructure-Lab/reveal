"""Resolve a call site to the one definition it reaches -- for the callee walk
(calls.index.walk_callees) that calls://?callees=X&depth=N answers from (and the retired
trace:// and ?root=).

A walk keyed by bare name merges every same-named function: two unrelated
`run()`s contribute each other's callees once either is reached. trace://
fixed that by walking definitions (BACK-1399); the recursive callees walk kept
the name-keyed BFS (BACK-1442). One walk now does both (BACK-2096) and resolves
each call site here: the caller's language family first (BACK-405), then what the
call is bound to -- a call whose qualifier or bare name an import binds reaches that
import's file, or is external when the import points outside the tree (BACK-2553) -- then a
same-file definition or the one its imports name, else the call is ambiguous and reported
as such, never guessed.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...analyzers.imports.bindings import Binding, file_bindings
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
        self._directory = directory  # the directory the definitions were collected from
        self._analysis: Any = None
        self._analysis_read = False
        self._bindings: Dict[str, Dict[str, Binding]] = {}
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
        if self._is_external(call, caller_file, candidates):
            return tail, None
        if len(candidates) == 1:
            return tail, candidates[0]
        return tail, self._disambiguate(call, tail, caller_file, candidates) or candidates

    def _is_external(self, call: str, caller_file: str, candidates: List[Definition]) -> bool:
        """The call's qualifier (``json`` of ``json.loads``) or bare name is bound by an import that
        points outside the tree, so a project function of that name is not what it reaches. A bare
        call to a name the file also defines reaches its own definition (it shadows the import)."""
        binding = self._file_bindings(caller_file).get(call.split('.')[0])
        if binding is None or not binding.external:
            return False
        return '.' in call or not any(c['file'] == caller_file for c in candidates)

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
        bindings = self._file_bindings(caller_file)
        binding = bindings.get(qualifier or (call if call in bindings else tail))
        imported = binding.target if binding else None
        imported_path = Path(imported).resolve() if imported else None
        via_import = [c for c in candidates if imported_path and Path(c['file']).resolve() == imported_path]
        same_file = [c for c in candidates if c['file'] == caller_file]
        for group in ((via_import, same_file) if qualifier else (same_file, via_import)):
            if len(group) == 1:
                return group[0]
        return None

    def _import_analysis(self) -> Any:
        """The walked directory's import analysis, resolved as imports:// resolves it
        (``project_scope``: from its project root, so an alias or sibling package above the
        directory counts) but built for the directory's own files only (a focused build,
        BACK-2565), or served from a cached whole-root build. Built on the first call that has
        candidates, not for a walk that never needs it."""
        if not self._analysis_read:
            self._analysis_read = True
            if self._directory is not None:
                from ...analyzers.imports import service
                self._analysis = service.analyze(service.project_scope(self._directory)).analysis
        return self._analysis

    def _file_bindings(self, file_path: str) -> Dict[str, Binding]:
        """The caller file's import bindings: from the import analysis when it holds the file, else
        the per-file symbol map (a file past the scan's file cap, or a file no import extractor
        reads), whose None never claims a target is external."""
        if file_path not in self._bindings:
            analysis = self._import_analysis()
            extraction = analysis.extractions.get(Path(file_path)) if analysis is not None else None
            if extraction is not None:
                self._bindings[file_path] = file_bindings(extraction.imports)
            else:
                from ..ast.call_graph import build_symbol_map
                self._bindings[file_path] = {name: Binding(target, False)
                                             for name, target in build_symbol_map(file_path).items()}
        return self._bindings[file_path]
