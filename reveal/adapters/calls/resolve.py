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

from ...analyzers.imports.bindings import ProjectBindings, reaches
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

    def capped_note(self) -> Optional[str]:
        """See ``ProjectBindings.capped_note``: set once a resolution has read the import analysis."""
        return self._bindings.capped_note()

    def has_import_target(self, call: str, caller_file: str, shadows: Tuple[str, ...] = ()) -> bool:
        """Whether an explicit import supplies target evidence for this call's binding.

        Reverse name queries keep their candidate policy without that evidence; a
        unique project name or a guessed receiver is not an explicit import proof.
        """
        qualifier = call.split('.')[0]
        if '.' in call and qualifier in shadows:
            return False
        binding = self._bindings.get(caller_file, qualifier)
        return binding is not None and binding.target is not None

    def resolve(self, call: str, caller_file: str, shadows: Tuple[str, ...] = ()) -> Tuple[str, Any]:
        """(bare name, target): target is one definition, a list of candidate
        definitions when the name stays ambiguous, or None when it reaches no project definition.
        ``shadows``: the call qualifiers the calling definition declares itself (a parameter or local
        ``src``), which no import binds there (BACK-2580)."""
        tail = _bare_callee_name(call)
        from ..ast.call_graph import build_alias_map
        if caller_file not in self._alias_maps:
            self._alias_maps[caller_file] = build_alias_map(caller_file)
        if '.' not in call:
            tail = self._alias_maps[caller_file].get(tail, tail)
        family = self._caller_family(caller_file)
        # A module is a call source (its top-level calls), never what a call reaches: Rust's
        # `mod parser;` is not the `parser(input)` a sibling calls (BACK-2569); nor is a class field
        # holding an object (`static max = new OffsetPair(...)`, BACK-2581).
        candidates = [d for d in self.index.get(tail, [])
                      if (not family or d['family'] == family) and d.get('category') != 'modules'
                      and d.get('callable', True) is not False]
        shadowed = '.' in call and call.split('.')[0] in shadows
        candidates = self._reachable(call, caller_file, candidates, shadowed)
        if not candidates:
            return tail, None
        if len(candidates) == 1:
            return tail, candidates[0]
        return tail, self._disambiguate(call, tail, caller_file, candidates, shadowed) or candidates

    def _reachable(self, call: str, caller_file: str, candidates: List[Definition],
                   shadowed: bool = False) -> List[Definition]:
        """The candidates the call can reach, given what its qualifier (``json`` of ``json.loads``)
        or bare name is bound to. Bound only by imports that resolved to no project file, it reaches
        none of them when they are outside the tree (BACK-2553), and when the verdict could not place
        them (``pytest``; a monorepo package root reveal does not model) only one whose file sits at
        the module's path (``dagster/_grpc/client.py`` for ``from dagster._grpc.client import f``,
        BACK-2573). A bare call to a name the file also defines reaches its own definition (it
        shadows the import)."""
        if shadowed:  # a local value: neither an import nor a language global binds it (BACK-2580/2581)
            return candidates
        binding = self._bindings.get(caller_file, call.split('.')[0])
        kept = reaches(binding, call, caller_file, (c['file'] for c in candidates))
        return [c for c in candidates if c['file'] in kept]

    def _caller_family(self, caller_file: str) -> str:
        if caller_file not in self._families:
            self._families[caller_file] = _lang_family(caller_file)
        return self._families[caller_file]

    def _disambiguate(self, call: str, tail: str, caller_file: str,
                      candidates: List[Definition], shadowed: bool = False) -> Optional[Definition]:
        """The one candidate the caller's own file or its imports point at.
        A bare call prefers a same-file definition (it shadows imports); a
        qualified one (`strings.rtrim`, `h.run`) prefers the module it names, and
        when an import binds its qualifier it reaches only that module (dagster's
        `click.group` is never dagster's own `def group`, BACK-2569)."""
        qualifier = call.split('.')[0] if '.' in call else ''
        via_import, bound = (([], False) if shadowed else
                             self._via_import(call, tail, qualifier, caller_file, candidates))
        same_file = [c for c in candidates if c['file'] == caller_file]
        groups = (via_import,) if qualifier and bound else (
            (via_import, same_file) if qualifier else (same_file, via_import))
        for group in groups:
            if len(group) == 1:
                return group[0]
        return None

    def _via_import(self, call: str, tail: str, qualifier: str, caller_file: str,
                    candidates: List[Definition]) -> Tuple[List[Definition], bool]:
        """(the candidates in the file the call's qualifier or bare name is imported from, narrowed to
        what the import names; whether an import names a file for it) (BACK-2569). A module binds a
        name once: a bare name, or a namespace's member, is a module-level definition, never a class's
        method of that name (three.js DataUtils.js: `function toHalfFloat` and `static toHalfFloat`),
        and of several (TypeScript overload signatures, a Python redefinition) the last, the one the
        module ends up binding. A call through an imported class (`SnapCache.getReferenceSnapPoints`)
        is that class's member. A package's ``__init__``/``index``/``mod`` that does not define the name
        re-exports it from inside the package: the candidates there (``click.group`` in
        click/decorators.py)."""
        binding = (self._bindings.get(caller_file, qualifier) if qualifier else
                   self._bindings.get(caller_file, call) or self._bindings.get(caller_file, tail))
        if binding is None or not binding.target:
            return [], False
        imported_path = Path(binding.target).resolve()
        via_import = [c for c in candidates if Path(c['file']).resolve() == imported_path]
        if not via_import and imported_path.stem in ('__init__', 'index', 'mod'):
            via_import = [c for c in candidates if imported_path.parent in Path(c['file']).resolve().parents]
        return (via_import if len(via_import) < 2 else _one_binding(via_import, qualifier, binding.origin)), True


def _one_binding(in_file: List[Definition], qualifier: str, origin: Optional[str]) -> List[Definition]:
    """Of several same-named definitions in the imported file, the one the import names: through an
    imported class, that class's member; else the last module-level one (the binding the module ends
    with); else all of them, still ambiguous."""
    if qualifier:
        owner = origin.rsplit('.', 1)[-1] if origin else qualifier
        owned = [c for c in in_file if c.get('owner') == owner]
        if owned:
            return owned[-1:]
    module_level = [c for c in in_file if not c.get('member')]
    return module_level[-1:] if module_level else in_file
