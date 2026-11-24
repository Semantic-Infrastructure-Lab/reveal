"""The element views' declared answer (BACK-2627, S3a design sections 1-4): ``reveal FILE [ELEMENT] --view VIEW``.

The path read's element views are one declared answer owned by the file route, as a declared noun's controls are owned
by its adapter: every control and every legacy flag is a ``ParamSpec`` here, the main parser's "Code analysis" group is
generated from them (``add_declared_arguments``) and the request is bound by the one binder, so Applicability, One
answer per request and Conflicting values come from these declarations (COMMAND_MODEL; X1). The views' modifiers follow
the COMMAND_MODEL rows: ``--depth`` is graph hops (``--transitive``), ``--nesting-depth`` structural depth (Depth row, D1);
flow's selectors are ``--kind``, a selection that repeats and combines (X3); effects keeps D10's strict modifiers (X4);
``--depth`` with ``--transitive`` is the one walk depth on every spelling, the legacy flags' included, refused outside
1..5 (X10's legacy clamp reversed, Scott 2026-11-24, BACK-2793); ``--range`` is the element selection (X9). The
vars, callsites and outputs homes wait on Scott (X5-X7): those operations stay standalone legacy operations with no new
spelling, and a later ``view=vars`` is an added choice.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Tuple

from .errors import NavRequestValidationError, RequestValidationError
from .utils.query_binding import (bind_prepared_params, bind_resource_path, boolean_value, prepare_declared_params,
                                  reject_two_answers, reject_unread_controls, string_value)
from .utils.query_parser import CliBinding, LegacySpelling, ParamSpec, ParamValueError, ResourceSpec, depth_param, \
    line_range, whole_number

ELEMENT_VIEWS = ('boundary', 'effects', 'flow', 'exits')
FLOW_KINDS = ('if', 'loop', 'try')
# The predicted result type of every element view (``_nav_json`` emits it), the first facet of each answer.
ELEMENT_ANSWER = 'element_view'
# The element answer reads one file: a directory refuses every element view by the resource's kind (E13, X2).
ELEMENT_RESOURCE = ResourceSpec(name='path', cli_default=None, uri_default=None, kind='file', walks=False)
_ONE_FILE = 'element views read one file: reveal FILE [ELEMENT] --view VIEW'


def _on(values: Mapping[str, Any], name: str) -> bool:
    """Whether switch *name* is on in a request's joined values (a ``rebinds_when`` test, not a read)."""
    try:
        return boolean_value(values.get(name) or False)
    except ValueError:  # an invalid switch value is the binder's error, reported on its own
        return False


def _in_loops(values: Mapping[str, Any]) -> bool:
    return _on(values, 'in-loops')


def _word(stands_for: str) -> Callable[[Any], Optional[str]]:
    """A no-value legacy flag as the value it stands for: the generated flag stores *stands_for*; a typed source may
    give the flag's presence (True). Off (False, None) is not given. A repeatable owner's flag appends, so a list of
    those is read the same way."""
    def codec(raw: Any) -> Optional[str]:
        items = raw if isinstance(raw, list) else [raw]
        if any(item is True or item == stands_for for item in items):
            return stands_for
        if all(item is False or item is None for item in items):
            return None
        raise ParamValueError(f'expected a flag or boolean, got {raw!r}')
    return codec


def parse_flow_selectors(value: str) -> Tuple[str, ...]:
    """The legacy ``--flow=SEL`` value: a nonempty comma union of if, loop and try, each once, in the order given."""
    parts = tuple(part.strip() for part in value.split(','))
    if any(part not in FLOW_KINDS for part in parts):
        raise ValueError('flow selectors must be nonempty comma-separated if, loop or try values')
    return tuple(dict.fromkeys(parts))


def _flow_selection(raw: Any) -> Optional[Tuple[str, ...]]:
    """Legacy ``--flow[=SEL]`` as kinds: bare (the flag's ``()``, or presence True) is every kind, so no ``--kind``;
    ``SEL`` is a comma union of if, loop and try (``parse_flow_selectors``'s rule). Off is not given."""
    items = raw if isinstance(raw, list) else [raw]
    if all(item is False or item is None for item in items):
        return None
    kinds: list = []
    for item in items:
        if item == () or item is True:
            continue
        if not isinstance(item, str):
            raise ParamValueError('flow selectors must be nonempty comma-separated if, loop or try values, '
                                  f'got {item!r}')
        try:
            kinds += parse_flow_selectors(item)
        except ValueError as exc:
            raise ParamValueError(str(exc)) from None
    return tuple(dict.fromkeys(kinds))


def flow_kinds(value: Any) -> Tuple[str, ...]:
    """``--kind`` on the flow view: each value one of if, loop, try; repeated values combine and an equal repeat is one
    term. A comma is no union syntax here (repeat the flag): ``--kind if,try`` is refused naming the kinds. A legacy
    ``--flow=if,try`` arrives already split, as nested items."""
    items = value if isinstance(value, (list, tuple)) else [value]
    kinds: list = []
    for item in items:
        if isinstance(item, (list, tuple)):
            kinds += flow_kinds(item)
        elif item in FLOW_KINDS:
            kinds.append(item)
        else:
            raise ParamValueError(f"kind must be one of {', '.join(FLOW_KINDS)} (repeat --kind to combine), "
                                  f'got {item!r}')
    return tuple(dict.fromkeys(kinds))


def nesting_depth(value: Any) -> int:
    """``--nesting-depth``: structural depth, a positive integer. A legacy structural flag's ``--depth`` binds here, so
    the refusal names both spellings."""
    depth = whole_number(value)
    if depth < 1:
        raise ParamValueError(f'nesting-depth (--depth on a legacy structural flag) must be a positive integer, '
                              f'got {value!r}')
    return depth


def _switch(name: str, description: str, **kwargs: Any) -> ParamSpec:
    return ParamSpec(name, 'boolean', description, False, boolean_value,
                     cli=CliBinding((f'--{name}',), action='store_true'), **kwargs)


def _view_word(name: str, view: str, **kwargs: Any) -> LegacySpelling:
    return LegacySpelling(name, flag=f'--{name}', flag_value=view, codec=_word(view), **kwargs)


def _kind_word(name: str, kind: str) -> LegacySpelling:
    return LegacySpelling(name, flag=f'--{name}', flag_value=kind, codec=_word(kind), sets=(('view', 'flow'),),
                          rebinds=(('depth', 'nesting-depth'),))


# The answers an element control is read by, as facets: ``view=V`` one view, an operation's name, ``view`` every view.
_SELECTED_LINES = ('view', 'inputs', 'outputs', 'callsites', 'varflow', 'keys')
_DEPTH_TO_NESTING = (('depth', 'nesting-depth'),)

VIEW = ParamSpec(
    'view', 'string', f"Element view: {', '.join(ELEMENT_VIEWS)}", None, string_value, choices=ELEMENT_VIEWS,
    role='operation', cli=CliBinding(('--view',), metavar='VIEW'),
    legacy=(_view_word('boundary', 'boundary'),
            _view_word('exits', 'exits'), _view_word('returns', 'exits'), _view_word('flowto', 'exits'),
            # D10: with --in-loops the legacy --effects spelling's --depth is structural, else the walk depth.
            _view_word('effects', 'effects', rebinds=_DEPTH_TO_NESTING, rebinds_when=_in_loops),
            _view_word('sideeffects', 'effects'),
            _view_word('fanout', 'effects', sets=(('in-loops', True),), rebinds=_DEPTH_TO_NESTING),
            _view_word('statewrites', 'effects', sets=(('state', True),)),
            # The code-element --outline: no generated flag (the main parser keeps --outline for file and Markdown
            # outlines); the file route gives it only for an element request on a code file (target:nav.outline).
            LegacySpelling('outline', codec=_word('flow'), rebinds=_DEPTH_TO_NESTING)))
KIND = ParamSpec(
    'kind', 'string', f"Flow view selection: {', '.join(FLOW_KINDS)}; repeat to combine", None, flow_kinds,
    repeatable=True, cli=CliBinding(('--kind',), metavar='KIND'), answers=('view=flow',),
    legacy=(LegacySpelling('flow', flag='--flow', flag_value=(), flag_optional=True, codec=_flow_selection,
                           sets=(('view', 'flow'),), rebinds=_DEPTH_TO_NESTING),
            _kind_word('ifmap', 'if'), _kind_word('loopmap', 'loop'), _kind_word('catchmap', 'try')))
IN_LOOPS = _switch('in-loops', 'Effects view: each loop with its classified effects; --nesting-depth defaults to 3',
                   answers=('view=effects',), requires=('state=false',))
STATE = _switch('state', 'Effects view: detected persistent and shared-state writes', answers=('view=effects',))
TRANSITIVE = _switch('transitive', 'Boundary or ordinary effects view: follow calls into project-local helpers '
                                   '(--depth hops, default 2, 1..5)',
                     answers=('view=boundary', 'view=effects'), requires=('in-loops=false', 'state=false'))
# The walk depth on every spelling of --transitive (BACK-2793): the main parser owns --depth, so its flag is reused.
DEPTH = depth_param('graph hops with --transitive (default 2)', answers=('view=boundary', 'view=effects'),
                    requires=('transitive=true',))
NESTING_DEPTH = ParamSpec('nesting-depth', 'integer', 'Structural depth of the flow view and of --in-loops (default 3)',
                          3, nesting_depth, minimum=1, cli=CliBinding(('--nesting-depth',), metavar='N'),
                          answers=('view=flow', 'view=effects'), requires=('view=flow|in-loops=true',))
RANGE = ParamSpec('range', 'string', 'Lines START-END of the element (1-indexed; START- is open-ended)', None,
                  line_range, cli=CliBinding(('--range',)), answers=_SELECTED_LINES,
                  # X9: --callsites N-M's own value is a second range; given beside --range, both name one selection.
                  requires=('callsites=FULL',))
# The standalone legacy operations (X5-X8 wait on Scott: no new spelling, no RETIREMENTS row of their own yet).
INPUTS = _switch('inputs', 'Candidate inputs to the selection (not the boundary view\'s inputs section)',
                 role='operation', legacy=(LegacySpelling('deps', flag='--deps'),))
OUTPUTS = _switch('outputs', 'Variables written in the selection and read after it', role='operation',
                  legacy=(LegacySpelling('mutations', flag='--mutations'), LegacySpelling('writes', flag='--writes')))
CALLSITES = ParamSpec('callsites', 'string', 'Call sites in the element, or in lines START-END', 'FULL', string_value,
                      role='operation', cli=CliBinding(('--callsites',), nargs='?', const='FULL', metavar='START-END'),
                      legacy=(LegacySpelling('calls', flag='--calls'),))
VARFLOW = ParamSpec('varflow', 'string', 'Reads and writes of one variable', None, string_value, role='operation',
                    names='symbol', cli=CliBinding(('--varflow',), metavar='VAR'))
KEYS = ParamSpec('keys', 'string', 'Keys read, written or tested on one variable', None, string_value,
                 role='operation', names='symbol', cli=CliBinding(('--keys',), metavar='VAR'))
NARROW = ParamSpec('narrow', 'string', 'How one annotated variable narrows through branches', None, string_value,
                   role='operation', names='symbol', cli=CliBinding(('--narrow',), metavar='VAR'))
CROSS_CALLS = _switch('cross-calls', 'Varflow: follow the variable across calls within the module',
                      answers=('varflow',))
SCOPE = _switch('scope', 'The ancestor scope chain of a :LINE', role='operation')
AROUND = ParamSpec('around', 'integer', 'N lines either side of a :LINE (default 20)', None, whole_number, minimum=0,
                   role='operation', cli=CliBinding(('--around',), nargs='?', const=20, metavar='N'))

# The path read's own controls, which the main parser owns for its other answers: declared here so an element request
# that gives one is judged (rows H and R of the design). The slices are read by the outline and element extraction,
# never by an element view; the grep and structural-query selectors select another answer of the path read.
HEAD = ParamSpec('head', 'integer', 'Path read: the first N rows', None, whole_number, cli=CliBinding(('--head',)),
                 answers=('code_element', 'file_structure'))
TAIL = ParamSpec('tail', 'integer', 'Path read: the last N rows', None, whole_number, cli=CliBinding(('--tail',)),
                 answers=('code_element', 'file_structure'))
GREP = ParamSpec('grep', 'string', 'Path read: the grep answer', None, string_value, role='operation',
                 cli=CliBinding(('--grep',)))
NAME = ParamSpec('name', 'string', 'Path read: the structural-query answer by name', None, string_value,
                 role='operation', cli=CliBinding(('--name',)))
TYPE = ParamSpec('type', 'string', 'Path read: the structural-query answer by element type', None, string_value,
                 role='operation', cli=CliBinding(('--type',)))
SORT = ParamSpec('sort', 'string', 'Path read: the structural-query answer\'s sort', None, string_value,
                 role='operation', cli=CliBinding(('--sort',)))

# The element answer's own controls: a request giving one of them (any spelling) is an element request.
_ELEMENT_CONTROLS: Tuple[ParamSpec, ...] = (VIEW, KIND, IN_LOOPS, STATE, TRANSITIVE, NESTING_DEPTH, INPUTS, OUTPUTS,
                                            CALLSITES, VARFLOW, KEYS, NARROW, CROSS_CALLS, SCOPE, AROUND)
# Read by element views and by other answers of the path read (tree and outline depth, outline slices).
_SHARED_CONTROLS: Tuple[ParamSpec, ...] = (DEPTH, RANGE)
_PATH_READ_CONTROLS: Tuple[ParamSpec, ...] = (HEAD, TAIL, GREP, NAME, TYPE, SORT)
ELEMENT_VIEW_SPECS: Tuple[ParamSpec, ...] = _ELEMENT_CONTROLS + _SHARED_CONTROLS + _PATH_READ_CONTROLS
# The operations that are not views (the order a request record names its one operation).
_OPERATIONS: Tuple[ParamSpec, ...] = tuple(spec for spec in _ELEMENT_CONTROLS if spec.role == 'operation'
                                           and spec is not VIEW)
# Every source key that spells an element control: the declarations' names and legacy words, derived (no hand list).
ELEMENT_KEYS = frozenset(key for spec in _ELEMENT_CONTROLS
                         for key in (spec.name, *spec.aliases, *(entry.name for entry in spec.legacy)))


def _given(value: Any) -> bool:
    return value is not None and value is not False and value != []


def element_request_given(source: Mapping[str, Any]) -> bool:
    """Whether a typed source gives any element control, in any spelling: only then is the element answer judged (the
    file outline, element extraction, the directory listing and the grep and query routes are not element requests)."""
    return any(_given(value) for key, value in source.items() if key in ELEMENT_KEYS)


@dataclass(frozen=True)
class ElementRequest:
    """The bound selection of one element request, which the handlers read instead of the argparse namespace. *view* is
    one of ``ELEMENT_VIEWS``, or None when a standalone legacy *operation* (inputs, outputs, callsites, varflow, keys,
    narrow, scope, around) is the answer, carrying *value*. *depth* is the transitive hop budget in effect (the given
    value, 1..5, or 2), None without ``--transitive``."""
    path: str
    element: Optional[str]
    view: Optional[str] = None
    operation: Optional[str] = None
    value: Any = None
    kind: Tuple[str, ...] = ()
    mode: Optional[str] = None
    transitive: bool = False
    depth: Optional[int] = None
    nesting_depth: int = 3
    range: Optional[Tuple[int, Optional[int]]] = None
    cross_calls: bool = False
    params: Any = field(default=None, compare=False, repr=False)  # the bound QueryParams (reads, given controls)
    spelled: Mapping[str, str] = field(default_factory=dict, compare=False, repr=False)  # key -> the flag typed

    @property
    def answer(self) -> str:
        """The selected answer: a view (effects by its mode, ``effects:loops``) or the operation."""
        if self.view == 'effects':
            return f'effects:{self.mode}'
        return self.view or self.operation or ''


def _effects_mode(params: Any) -> str:
    return 'loops' if IN_LOOPS.read(params) else 'state' if STATE.read(params) else 'ordinary'


def _operation(params: Any) -> Tuple[Optional[str], Any]:
    """The standalone operation a bound request selects and its value (None for a switch such as ``--scope``)."""
    spec = next((spec for spec in _OPERATIONS if spec.name in params._given and spec.read(params) is not False), None)
    if spec is None:
        return None, None
    return spec.name, spec.read(params) if spec.type != 'boolean' else None


def _hop_budget(params: Any, transitive: bool) -> Optional[int]:
    """The transitive hop budget in effect: the given value (1..5, refused outside it) or the default 2; None without
    ``--transitive``."""
    if 'depth' in params._given:
        return int(DEPTH.read(params))
    return 2 if transitive else None


def _given_value(spec: ParamSpec, params: Any, absent: Any = None) -> Any:
    return spec.read(params) if spec.name in params._given else absent


def _request(params: Any, path: str, element: Optional[str], spelled: Mapping[str, str]) -> ElementRequest:
    view = _given_value(VIEW, params)
    operation, value = _operation(params)
    transitive = bool(TRANSITIVE.read(params))
    return ElementRequest(
        path=path, element=element, view=view, operation=operation, value=value,
        kind=tuple(_given_value(KIND, params, ())), mode=_effects_mode(params) if view == 'effects' else None,
        transitive=transitive, depth=_hop_budget(params, transitive), nesting_depth=NESTING_DEPTH.read(params),
        range=_given_value(RANGE, params), cross_calls=bool(CROSS_CALLS.read(params)), params=params, spelled=spelled)


def bind_element_request(source: Mapping[str, Any], spelled: Optional[Mapping[str, str]] = None, *, path: str,
                         element: Optional[str] = None) -> Optional[ElementRequest]:
    """The one binding of an element request, for the CLI route (a typed source read off the main parser's namespace by
    ``declared.typed_source``) and MCP ``reveal_nav`` (a typed source it builds). None when the source gives no element
    control. Otherwise: the path must be a file (a directory refuses every element view, X2/E13), the controls bind
    through the declarations (legacy flags translated, conflicting values, one answer per request) and each given
    control must be read by the selected answer or meet what it requires (Applicability, D10). Every refusal is the
    navigation owner's NavRequestValidationError (an invalid request, exit 2) naming what the request gave. *element* None is the whole file (flat mode)."""
    if not element_request_given(source):
        return None
    # An omitted control (None) or a switch given off (False) is not given, whichever caller built the source (the
    # CLI's generated flags omit them; a library namespace or MCP may carry them).
    source = {key: value for key, value in source.items() if _given(value)}
    try:
        return _bound(source, spelled, path, element)
    except NavRequestValidationError:
        raise
    except ValueError as exc:  # the binder's refusals, a conflicting spelling, a legacy value a codec rejects
        raise NavRequestValidationError(str(exc)) from exc


def _bound(source: Mapping[str, Any], spelled: Optional[Mapping[str, str]], path: str,
           element: Optional[str]) -> ElementRequest:
    try:  # a missing path is the source read's failure to report (NavSourceFailure), not a kind refusal
        bind_resource_path(ELEMENT_RESOURCE, path, transport='typed', validate_kind=Path(path).exists())
    except RequestValidationError as exc:
        raise NavRequestValidationError(f'{exc}; {_ONE_FILE}') from exc
    params = prepare_declared_params(ELEMENT_VIEW_SPECS, source, 'typed', spelled=spelled)
    params = bind_prepared_params(ELEMENT_VIEW_SPECS, params, transport='typed')
    reject_two_answers(ELEMENT_VIEW_SPECS, params)
    reject_unread_controls(ELEMENT_VIEW_SPECS, params, lambda: ELEMENT_ANSWER)
    return _request(params, path, element, dict(spelled or {}))
