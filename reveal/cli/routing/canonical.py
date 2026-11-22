"""A bound request rendered as the canonical request of each transport (BACK-2716 step 2).

One request, three spellings that answer with equal JSON and exit: the CLI and ``--stdin`` line
(``reveal calls src --callers main``), MCP (``reveal_run(["calls", "src", "--callers", "main"])``) and Python
(``api.query("calls", "src", callers="main")``). The words come from the noun's declarations, never a hand table:
the controls the request gave, in declaration order, each as the first long flag its parser reads, with the value
spelled as ``typed_words`` spells it, so the Python form is the inverse of what ``api.query`` accepts and the CLI
form is what the noun parser parses.
"""
import json
import shlex
import argparse
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ...utils.query_binding import switch_value


FORMS = ('cli', 'mcp', 'python')

# The walk's request controls every walking noun's parser carries beside its declared ones.
_WALK_CONTROLS = ('all', 'exclude', 'respect_gitignore')


def _request_dests(adapter: Any) -> set:
    from ...utils.query_binding import legacy_flag_dests
    dests = set(_WALK_CONTROLS) | set(getattr(adapter, 'CLI_PRESENTATION_FLAGS', ()))
    if callable(getattr(adapter, 'reconfigure_base_path', None)):
        dests.add('base_path')
    for spec in adapter.PARAM_SPECS:
        if spec.cli is not None:
            dests.add(spec.cli.dest or spec.name)
        dests.update(legacy_flag_dests(spec))
    # The global --verbose binds where verbose_binding takes it (the noun's legacy word, else detail=full), so the
    # keyword answers as the flag does (BACK-2622: api.query('overview', P, verbose=True) was an unsupported control).
    if any('verbose' in spec.spellings or spec.name == 'detail' for spec in adapter.PARAM_SPECS):
        dests.add('verbose')
    return dests


def typed_options(parser: argparse.ArgumentParser, adapter: Any) -> Dict[str, Tuple[str, argparse.Action]]:
    """keyword -> (the long flag it writes, its action), for every request control the noun's *parser* reads."""
    dests = _request_dests(adapter)
    options: Dict[str, Tuple[str, argparse.Action]] = {}
    for action in parser._actions:
        if action.dest not in dests:
            continue
        for flag in action.option_strings:
            if flag.startswith('--'):
                options.setdefault(flag[2:].replace('-', '_'), (flag, action))
    return options


def _value_word(keyword: str, flag: str, action: argparse.Action, item: Any) -> str:
    """One value after *flag*: ``--flag=VALUE`` (a value that starts with '-' stays a value), a bare ``--flag`` for
    True on a flag whose value is optional, ``true``/``false`` for any other boolean."""
    from ...errors import RequestValidationError
    if isinstance(item, bool):
        if item and action.nargs == '?':
            return flag
        item = 'true' if item else 'false'
    elif not isinstance(item, (str, int, float)):
        raise RequestValidationError(f'{keyword} takes a string or number, got {type(item).__name__}')
    return f'{flag}={item}'


def _flag_words(keyword: str, flag: str, action: argparse.Action, value: Any) -> List[str]:
    """The words *value* is spelled as after *flag*; None, and False on a flag that takes no value, select nothing
    (the declared default)."""
    from ...errors import RequestValidationError
    if value is None:
        return []
    if action.nargs == 0:
        if not isinstance(value, bool):
            raise RequestValidationError(f'{keyword} takes True or False, got {value!r}')
        return [flag] if value else []
    values = list(value) if isinstance(value, (list, tuple)) else [value]
    if action.nargs == '+':  # one flag, then its words: --tests a b
        return [flag, *(_value_word(keyword, flag, action, item).partition('=')[2] for item in values)]
    if len(values) > 1 and not isinstance(action, argparse._AppendAction):
        raise RequestValidationError(f'{keyword} takes one value, got {len(values)}')
    return [_value_word(keyword, flag, action, item) for item in values]


def typed_words(parser: argparse.ArgumentParser, adapter: Any, controls: Mapping[str, Any]) -> List[str]:
    """The noun's flags for *controls*; a keyword that names no request control is the unsupported-control error
    (``UnsupportedOverrideError``, rule 3's message), raised before anything runs."""
    options = typed_options(parser, adapter)
    unknown = [keyword for keyword in controls if keyword not in options]
    if unknown:
        from ...errors import UnsupportedOverrideError
        from ...utils.query_binding import unsupported_controls_message
        raise UnsupportedOverrideError(unsupported_controls_message(adapter.PARAM_SPECS, unknown))
    words: List[str] = []
    for keyword, value in controls.items():
        flag, action = options[keyword]
        words.extend(_flag_words(keyword, flag, action, value))
    return words


class UnrenderableRequest(ValueError):
    """A request that gives a control no flag of its noun spells: it has no canonical form to recommend, so it says no
    request note (a standalone legacy word keeps its own row's note)."""


def spec_flag(spec: Any, parser: argparse.ArgumentParser, adapter: Any) -> Optional[str]:
    """The long flag that spells *spec*: its own first one, never a legacy flag that shares its dest (calls: --target also
    writes callers); a spec with no CLI binding of its own is read by the parser's flag whose dest is its name (the walk's
    ``--all`` and ``--respect-gitignore``, the global ``--format``), unless another declaration binds that flag: Claude's
    ``--tail`` is the flag-only row slice (``tail_rows``), not the legacy ``?tail`` turn slice."""
    if spec.cli is not None:
        return next((flag for flag in spec.cli.flags if flag.startswith('--')), None)
    bound = {flag for other in adapter.PARAM_SPECS if other.cli is not None for flag in other.cli.flags}
    for action in parser._actions:
        if action.dest == spec.name:
            flag = next((flag for flag in action.option_strings if flag.startswith('--')), None)
            return None if flag in bound else flag
    return None


def _given_flags(parser: Any, adapter: Any, params: Mapping[str, Any]) -> List[Tuple[Any, str]]:
    """(spec, flag) for every declared control *params* gave, in declaration order; a given control no flag spells raises
    ``UnrenderableRequest`` (recommending the request without it would recommend a different request)."""
    from ...utils.query_binding import given_controls
    given = given_controls(params)
    flags = []
    for spec in adapter.PARAM_SPECS:
        if spec.name not in given:
            continue
        flag = spec_flag(spec, parser, adapter)
        if flag is None:
            raise UnrenderableRequest(f'{spec.name} has no flag on this noun')
        flags.append((spec, flag))
    return flags


def canonical_where_terms(spec: Any, terms: List[Any]) -> List[Any]:
    """*terms* of a where control on their canonical fields: a retired field that answers as another field is spelled as
    that field (``type!=x`` is ``kind!=x``); a retired field without one has no canonical form (``UnrenderableRequest``)."""
    from ...utils.query_binding import where_fields
    from ...utils.query_parser import QueryParams
    words = dict(spec.field_words)
    canonical = []
    for term in terms:
        field = next(iter(where_fields(QueryParams({spec.name: [term]}), spec)), '')
        if field in spec.retired_fields:
            if field not in words:
                raise UnrenderableRequest(f'where field {field!r} retired with no canonical field')
            text = str(term)
            start = text.index(field)
            term = text[:start] + words[field] + text[start + len(field):]
        canonical.append(term)
    return canonical


def canonical_controls(parser: Any, adapter: Any, params: Mapping[str, Any],
                       walk_policy: Optional[bool] = None) -> Dict[str, Any]:
    """keyword -> value for every request control *params* gave, in declaration order.

    *params* is a bound ``QueryParams`` (after ``prepare_declared_params`` and ``join_uri_and_flags``: legacy words are
    already translated, ``top=5`` is ``limit``). *walk_policy* is a URI's ``respect_gitignore`` value, which every URI
    entry point splits off before binding (``split_respect_gitignore``): ``--respect-gitignore on|off``. A presentation
    flag the request gave (``--format``) is no request control: ``presentation_words`` spells it for the CLI and MCP
    forms, and a Python answer is the JSON document."""
    options = typed_options(parser, adapter)
    controls: Dict[str, Any] = {}
    if walk_policy is not None and 'respect_gitignore' in options:
        controls['respect_gitignore'] = 'on' if walk_policy else 'off'
    for spec, flag in _given_flags(parser, adapter, params):
        keyword = flag[2:].replace('-', '_')
        if keyword in options:
            value = _flag_value(spec, _unread(params, spec.name))
            if spec.retired_values and value in spec.retired_values:
                raise UnrenderableRequest(f'{spec.name}={value} is a retired value with no canonical form')
            if spec.retired_fields and isinstance(value, (list, tuple)):
                value = canonical_where_terms(spec, list(value))
            if spec.convert is switch_value and isinstance(value, bool):
                value = 'on' if value else 'off'  # a switch is spelled on|off (COMMAND_MODEL "Switches", BACK-2622)
            controls[keyword] = value
    return controls


def presentation_words(parser: Any, adapter: Any, params: Mapping[str, Any]) -> List[str]:
    """The words of the presentation flags *params* gave (a URI's ``?format=dot`` is ``--format=dot``)."""
    options = typed_options(parser, adapter)
    words: List[str] = []
    for spec, flag in _given_flags(parser, adapter, params):
        if flag[2:].replace('-', '_') not in options:
            action, value = parser._option_string_actions[flag], _flag_value(spec, _unread(params, spec.name))
            if action.choices is not None and value not in action.choices:  # calls ?format=dot: --format has no dot
                raise UnrenderableRequest(f'{flag} does not offer {value!r}')
            words.extend(_flag_words(spec.name, flag, action, value))
    return words


def _unread(params: Mapping[str, Any], name: str) -> Any:
    """A bound value without recording that the answer read it: ``QueryParams`` marks every ``[]`` and ``get`` as a read,
    and the answer's own unread-control checks must see exactly what the request gave."""
    return dict.__getitem__(params, name)  # type: ignore[index]


def _flag_value(spec: Any, raw: Any) -> Any:
    """One bound control as its flag takes it: a URI-spelled value decoded as the binder decodes it, and a comma-separated
    list (``?columns=a,b``) as the one comma-joined value its flag reads (``--columns a,b``), unless the flag repeats or takes
    several words."""
    from ...utils.query_binding import _decode_value
    value = spec.validate(_decode_value(spec, raw))
    one_word = spec.cli_action != 'append' and getattr(spec.cli, 'nargs', None) != '+'
    if isinstance(value, (list, tuple)) and one_word:
        return ','.join(str(item) for item in value)
    return value


def _cli_words(words: List[str]) -> List[str]:
    """``--flag=VALUE`` as the two words ``--flag VALUE``, except a value that starts with '-' (it stays one word, so
    the parser cannot read it as an option)."""
    spelled: List[str] = []
    for word in words:
        flag, equals, value = word.partition('=')
        if equals and flag.startswith('--') and value and not value.startswith('-'):
            spelled.extend((flag, value))
        else:
            spelled.append(word)
    return spelled


def _target_words(target: Optional[str], words: List[str]) -> List[str]:
    """The target first, after '--' when it would read as an option."""
    if target is None:
        return words
    if target.startswith('-'):
        return [*words, '--', target]
    return [target, *words]


def cli_argv(noun: str, target: Optional[str], words: List[str]) -> List[str]:
    """The argv after ``reveal`` that runs the request (what MCP's ``reveal_run`` takes)."""
    return [noun, *_target_words(target, _cli_words(words))]


def _python_value(value: Any) -> str:
    return repr(value)


def python_call(noun: str, target: Optional[str], controls: Mapping[str, Any]) -> str:
    """``api.query("calls", "src", callers="main")``; a keyword that is a Python keyword goes in ``**{...}``."""
    import keyword as pykeyword
    args = [json.dumps(noun)]
    if target is not None:
        args.append(json.dumps(target))
    plain = [f'{key}={_python_value(value)}' for key, value in controls.items() if not pykeyword.iskeyword(key)]
    reserved = {key: value for key, value in controls.items() if pykeyword.iskeyword(key)}
    args.extend(plain)
    if reserved:
        args.append('**{' + ', '.join(f'{json.dumps(key)}: {_python_value(value)}' for key, value in reserved.items()) + '}')
    return f'api.query({", ".join(args)})'


def render_request(form: str, noun: str, target: Optional[str], params: Mapping[str, Any], *,
                   parser: argparse.ArgumentParser, adapter: Any, walk_policy: Optional[bool] = None,
                   presentation: bool = True) -> str:
    """The canonical request for a bound request, in the *form* of one transport (``FORMS``). *parser* and *adapter* are
    the noun's declared parser and adapter class, given by the caller: this module reads declarations and imports no
    router (the router imports it). *walk_policy*: ``canonical_controls``. *presentation* False leaves out the request's
    presentation flags: the invocation typed its own ``--format``/``--output``, which the URI's lost to."""
    if form not in FORMS:
        raise ValueError(f'form is one of {FORMS}, not {form!r}')
    controls = canonical_controls(parser, adapter, params, walk_policy)
    if form == 'python':
        return python_call(noun, target, controls)
    shown = presentation_words(parser, adapter, params) if presentation else []
    argv = cli_argv(noun, target, [*typed_words(parser, adapter, controls), *shown])
    if form == 'mcp':
        return f'reveal_run({json.dumps(argv)})'
    return 'reveal ' + shlex.join(argv)


def render_uri_request(form: str, scheme: str, resource: str, params: Mapping[str, Any], *,
                       parser: argparse.ArgumentParser, adapter: Any, walk_policy: Optional[bool] = None,
                       presentation: bool = True) -> str:
    """What a URI request is a retiring spelling of, in one transport's form (BACK-2716 step 3). An analysis-only
    scheme names a path and selects an analysis: ``reveal NOUN TARGET --flags``. A resource keeps its address and takes
    the flags: ``reveal git://app.py@main --limit 5``; on MCP that is ``reveal_run(["git://app.py@main", ...])`` and in
    Python ``api.query("git://app.py@main", limit=5)``. *walk_policy*, *presentation*: ``render_request``."""
    if getattr(adapter, 'ANALYSIS_ONLY', False):
        return render_request(form, scheme, resource or None, params, parser=parser, adapter=adapter,
                              walk_policy=walk_policy, presentation=presentation)
    controls = canonical_controls(parser, adapter, params, walk_policy)
    uri = f'{scheme}://{resource}'
    if form == 'python':
        call = python_call(scheme, None, controls)
        return call.replace(f'api.query({json.dumps(scheme)}', f'api.query({json.dumps(uri)}', 1)
    words = [*typed_words(parser, adapter, controls), *(presentation_words(parser, adapter, params) if presentation else [])]
    argv = [*_target_words(uri, _cli_words(words))]
    if form == 'mcp':
        return f'reveal_run({json.dumps(argv)})'
    return 'reveal ' + shlex.join(argv)
