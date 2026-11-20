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


def canonical_controls(parser: Any, adapter: Any, params: Mapping[str, Any]) -> Dict[str, Any]:
    """keyword -> value for every declared control *params* gave, in declaration order.

    *params* is a bound ``QueryParams`` (after ``prepare_declared_params`` and ``join_uri_and_flags``: legacy words are
    already translated, ``top=5`` is ``limit``). A control that has no keyword (no long flag the parser reads) is the
    request's own spelling problem and is left out; the round-trip test shows it."""
    from ...utils.query_binding import given_controls
    options = typed_options(parser, adapter)
    given = given_controls(params)
    controls: Dict[str, Any] = {}
    for spec in adapter.PARAM_SPECS:
        if spec.name not in given or spec.cli is None:
            continue
        # The spec's own first long flag, never a legacy flag that shares its dest (calls: --target also writes callers).
        own = next((flag for flag in spec.cli.flags if flag.startswith('--')), None)
        keyword = own[2:].replace('-', '_') if own else None
        if keyword not in options:
            continue
        controls[keyword] = _flag_value(spec, _unread(params, spec.name))
    return controls


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
    one_word = spec.cli_action != 'append' and spec.cli.nargs != '+'
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
                   parser: argparse.ArgumentParser, adapter: Any) -> str:
    """The canonical request for a bound request, in the *form* of one transport (``FORMS``). *parser* and *adapter* are
    the noun's declared parser and adapter class, given by the caller: this module reads declarations and imports no
    router (the router imports it)."""
    if form not in FORMS:
        raise ValueError(f'form is one of {FORMS}, not {form!r}')
    controls = canonical_controls(parser, adapter, params)
    if form == 'python':
        return python_call(noun, target, controls)
    argv = cli_argv(noun, target, typed_words(parser, adapter, controls))
    if form == 'mcp':
        return f'reveal_run({json.dumps(argv)})'
    return 'reveal ' + shlex.join(argv)


def render_uri_request(form: str, scheme: str, resource: str, params: Mapping[str, Any], *,
                       parser: argparse.ArgumentParser, adapter: Any) -> str:
    """What a URI request is a retiring spelling of, in one transport's form (BACK-2716 step 3). An analysis-only
    scheme names a path and selects an analysis: ``reveal NOUN TARGET --flags``. A resource keeps its address and takes
    the flags: ``reveal git://app.py@main --limit 5``; on MCP that is ``reveal_run(["git://app.py@main", ...])`` and in
    Python ``api.query("git://app.py@main", limit=5)``."""
    if getattr(adapter, 'ANALYSIS_ONLY', False):
        return render_request(form, scheme, resource or None, params, parser=parser, adapter=adapter)
    controls = canonical_controls(parser, adapter, params)
    uri = f'{scheme}://{resource}'
    if form == 'python':
        call = python_call(scheme, None, controls)
        return call.replace(f'api.query({json.dumps(scheme)}', f'api.query({json.dumps(uri)}', 1)
    argv = [*_target_words(uri, _cli_words(typed_words(parser, adapter, controls)))]
    if form == 'mcp':
        return f'reveal_run({json.dumps(argv)})'
    return 'reveal ' + shlex.join(argv)
