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
from typing import Any, Dict, List, Mapping, Optional

from .typed import _noun_adapter, typed_options, typed_words

FORMS = ('cli', 'mcp', 'python')


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
        controls[keyword] = _flag_value(spec, dict.__getitem__(params, spec.name))  # no read is recorded
    return controls


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


def render_request(form: str, noun: str, target: Optional[str], params: Mapping[str, Any]) -> str:
    """The canonical request for a bound request, in the *form* of one transport (``FORMS``)."""
    if form not in FORMS:
        raise ValueError(f'form is one of {FORMS}, not {form!r}')
    from .declared import create_declared_parser
    adapter_name, adapter = _noun_adapter(noun)
    parser = create_declared_parser(adapter_name)
    controls = canonical_controls(parser, adapter, params)
    if form == 'python':
        return python_call(noun, target, controls)
    argv = cli_argv(noun, target, typed_words(parser, adapter, controls))
    if form == 'mcp':
        return f'reveal_run({json.dumps(argv)})'
    return 'reveal ' + shlex.join(argv)


def render_uri_request(form: str, scheme: str, resource: str, params: Mapping[str, Any]) -> str:
    """What a URI request is a retiring spelling of, in one transport's form (BACK-2716 step 3). An analysis-only
    scheme names a path and selects an analysis: ``reveal NOUN TARGET --flags``. A resource keeps its address and takes
    the flags: ``reveal git://app.py@main --limit 5``; on MCP that is ``reveal_run(["git://app.py@main", ...])`` and in
    Python ``api.query("git://app.py@main", limit=5)``."""
    from ...adapters.base import get_adapter_class
    if getattr(get_adapter_class(scheme), 'ANALYSIS_ONLY', False):
        return render_request(form, scheme, resource or None, params)
    adapter_name, adapter = _noun_adapter(scheme)
    from .declared import create_declared_parser
    parser = create_declared_parser(adapter_name)
    controls = canonical_controls(parser, adapter, params)
    uri = f'{scheme}://{resource}'
    if form == 'python':
        call = python_call(scheme, None, controls)
        return call.replace(f'api.query({json.dumps(scheme)}', f'api.query({json.dumps(uri)}', 1)
    argv = [*_target_words(uri, _cli_words(typed_words(parser, adapter, controls)))]
    if form == 'mcp':
        return f'reveal_run({json.dumps(argv)})'
    return 'reveal ' + shlex.join(argv)
