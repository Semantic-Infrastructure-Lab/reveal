#!/usr/bin/env python3
"""Rewrite the documented URI-request examples as the canonical request the request note recommends (BACK-2726).

A documented command whose first word is a retiring URI request (an analysis-only scheme, or any URI spelling a query
string; BACK-2716) is rewritten as the executable canonical request rendered from the bound request by the request
note's renderers in ``reveal.cli.routing.canonical``: ``reveal NOUN TARGET --flags`` (``render_request``) where the
noun declares a subcommand and the target is a plain path, the resource URI followed by flags (``render_uri_request``)
where the URI carries an address (a JSON key path, ``@ref``, a session; D1, D20). "Plain path" is read from the noun's
declarations, never a table here (``plain_path``), and kept only when the subcommand rendering round-trips. Nothing here
parses a URI or finds an example on its own:

  examples   ``scripts/doc_examples.py``, the executable-docs gate's extractor (fenced bash/sh/shell blocks and embedded
             Markdown tables) and its ``retiring_uri_index`` check (the ``.github/doc_uri_requests_baseline.json``
             ratchet counts ``documented_uri_requests``);
  binding    ``reveal.api._bound_uri_params``, the binding ``reveal.api._note_uri_request`` and the answer share (the
             walk policy split off, then the binder's ``prepare_declared_params(..., 'uri')``); a request it refuses is
             reported with the binder's own error;
  rendering  ``render_request`` / ``render_uri_request`` (form ``cli``), with the request's typed ``--format``/
             ``--output`` kept as the note keeps it (``presentation=False``); a subcommand rendering the noun parser does
             not read back with the URI's resource keeps the resource form, counted; a replacement that spells a
             word with a RETIREMENTS row (a flag, a flag value, a control) is refused (``retiring_words``);
  context    ``scripts/check_retired_names.py`` ``REPLACED_BY_CONTEXT``: a command line that says its spelling is
             deprecated (an inline ``# deprecated`` comment) is left, as prose naming a retired spelling is.

The extra pass (BACK-2726 step 7): a line already written in the resource form, ``reveal SCHEME://PLAIN --flags`` (no
query string, at least one flag after it), is rewritten to ``reveal NOUN PLAIN --flags`` when the same plain-path rule
says so (``plain_path``) and the subcommand round-trips; a resource line naming an address is no example at all.

Only the URI word changes: words before it, flags after it (BACK-2673: flags after a URI are the subcommand's flags),
pipes and comments stay as written. A command continued with backslashes over several lines is rewritten on the physical
line that holds its URI word, its first, and the joined command's words must be the old ones with that word replaced
(``_continued_first_line``). A ``<placeholder>`` in the URI's address part (``claude://session/<session-name>``) binds
as a plain stand-in name and comes back quoted in the rendered line (``address_slots``). An example is left, with the reason counted, when the doc shows it failing, it names
its spelling as deprecated, it is not on one line of the file (an argument quoted across lines, or a URI word after the
first physical line), it holds a shell variable or a placeholder in a query value, a control it gives has no flag
(``UnrenderableRequest``),
the binder rejects it, a flag after the URI gives a control the URI gives too, the rendered line does not parse with
the noun's parser, the replacement would spell a word that itself retires, or its scheme says no request note (a retired
twin with its own ``scheme:`` row). An ops scheme's query string is no retiring request at all (D13), so it is no
example. Prose is never edited: inline backtick commands and other URI mentions outside executable
blocks are counted as ``prose`` for the report only.

Usage:
  python scripts/migrate_doc_uri_examples.py --check [DOC...]        # dry run: per-file counts, nothing written
  python scripts/migrate_doc_uri_examples.py --check --show [DOC...] # also each before/after and each left reason
  python scripts/migrate_doc_uri_examples.py --write DOC...          # rewrite those docs in place
  python scripts/migrate_doc_uri_examples.py --check --format json   # the plan as JSON

With no DOC, every source the extractor reads (AGENT_HELP, guides, adapter guides, README, QUICK_START, WHY_REVEAL,
INDEX). ``--write`` needs explicit paths. A DOC the extractor does not read is reported as such and never written.
"""
import argparse
import json
import os
import re
import shlex
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.doc_examples import documented_commands, documented_uri_requests, retiring_uri_index  # noqa: E402
from scripts.doc_examples import documented_sources as _extractor_sources  # noqa: E402

DOCS = ROOT / 'reveal' / 'docs'

# Why an example is left as written; every left example carries exactly one.
SHOWN_FAILING = 'the doc shows it failing'
NAMES_DEPRECATED = 'its line names the spelling as deprecated'
SHOWS_THE_URI = 'its comment presents it as the URI spelling of a neighbouring line: by hand'
OTHER_NOUN = 'its noun is outside --noun'
NOT_ONE_LINE = 'not on one line of the file (a multi-line argument, or a URI after the first physical line)'
NOT_LOCATED = 'the URI word is not spelled as one quoted or bare word'
PLACEHOLDER = 'a $VARIABLE in the URI, or a <placeholder> in a query value: by hand'
NO_REQUEST_NOTE_TWIN = 'retired twin scheme: its own scheme: row is the note, not a request note'
UNRENDERABLE = 'no canonical form'  # + the renderer's reason
BINDER_REJECTS = 'the binder rejects the request'  # + the binder's message
BOTH_SPELL = 'a flag after the URI gives a control the URI gives too'
DOES_NOT_PARSE = 'the rendered line does not parse with the noun parser'  # + the parser's message
RETIRING_REPLACEMENT = 'the replacement spells a word that itself retires'  # + the RETIREMENTS keys
EMBEDDED = 'an embedded Markdown table cell: by hand'
COPY_LEFT = 'a copy of this line elsewhere in the file is left (lines are rewritten by text)'
SEVERAL_COMMANDS = 'another reveal command follows on the line (the extractor reads the first): by hand'
NO_ROUND_TRIP = 'the subcommand rendering does not round-trip: the resource line stays'

# A comment that presents the example as the other spelling of a neighbouring command ("# the same answer as a URI"):
# rewritten, it would repeat that command under a false comment.
URI_COMMENT = re.compile(r'\bURI\b|\bsame (?:answer|request|result)\b|query[- ]param', re.IGNORECASE)
# The extractor's placeholder shape (tests/test_example_recipes_run.py ``_named_fixture_skip``), and shell variables
# ($file, ${x}, $(cmd)); a regex anchor (name~=Manager$) is a value.
ANGLE_PLACEHOLDER = re.compile(r'<[A-Za-z_-]+>')
SHELL_VARIABLE = re.compile(r'\$[A-Za-z_{(]')
SLOT = 'revealslot{}'  # an address placeholder's stand-in while the request binds and renders: a plain name
PROSE_URI = re.compile(r'\b([a-z]+)://[^\s`\'")\]|]*\?[^\s`\'")\]|]*')
_SHELL_WORDS = {'|', '||', '&&', ';', '>', '>>', '2>&1', '2>/dev/null'}


@dataclass
class Bound:
    scheme: str
    resource: str
    params: object
    walk_policy: Optional[bool]
    adapter: object
    parser: object


def bind_uri(uri: str) -> Bound:
    """The request a URI binds: ``reveal.api._bound_uri_params``, the binding the request note and the answer share."""
    from reveal.api import _bound_uri_params
    from reveal.cli.routing.declared import create_declared_parser
    scheme = uri.partition('://')[0]
    bound = _bound_uri_params(scheme, uri, {})
    if bound is None:
        raise _binder_refusal(scheme, uri)
    adapter, resource, params, walk_policy = bound
    parser = create_declared_parser(scheme)
    parser.raise_usage_errors = True
    return Bound(scheme, resource, params, walk_policy, adapter, parser)


def _binder_refusal(scheme: str, uri: str) -> Exception:
    """The binder's own error for a URI ``_bound_uri_params`` refuses: the helper answers None and leaves the reason to the
    answer, and this report names it, so the one step that raises (``prepare_declared_params``) runs again for it."""
    from reveal.cli.routing.declared import declared_adapter_class
    from reveal.utils.gitignore import split_respect_gitignore
    from reveal.utils.query_binding import prepare_declared_params
    query = split_respect_gitignore(uri.partition('://')[2])[0].partition('?')[2]
    try:
        prepare_declared_params(declared_adapter_class(scheme).PARAM_SPECS, query, 'uri')
    except (ValueError, TypeError) as exc:
        return exc
    return ValueError(f'{uri}: the request binds no declared request')


def _stage(tokens: Sequence[str], start: int) -> List[str]:
    """The reveal command's own words from *start*: up to a pipe, shell operator or redirection."""
    words = []
    for token in tokens[start:]:
        if token in _SHELL_WORDS or token.startswith(('>', '2>')):
            break
        words.append(token)
    return words


def _typed_presentation(words: Sequence[str]) -> bool:
    return any(w.partition('=')[0] in ('--format', '--output') for w in words)


def plain_path(bound: Bound) -> bool:
    """Whether the URI's resource is a plain path, from the noun's declarations (no per-noun table): its subcommand's
    positional is a path (``RESOURCE_SPEC.name``; Claude's and Codex's is a ``resource``: sessions, a session id, a named
    resource), the resource holds none of the address marks the noun declares (``RESOURCE_SPEC.address``: git's
    ``app.py@main``), and the declared ``resource_path`` hook, the part a path preflight resolves, is the whole resource
    (a JSON key path ``data.json/users``, Calls' ``path:name``). A noun need not walk the filesystem: git's paths name
    files in a repository (``filesystem=False``) and are plain paths all the same."""
    spec = bound.adapter.RESOURCE_SPEC
    if spec.name != 'path' or any(mark in bound.resource for mark in spec.address):
        return False
    resolve = getattr(bound.adapter, 'resource_path', None)
    if not callable(resolve) or not bound.resource:
        return True
    return Path(os.path.expanduser(resolve(bound.resource))) == Path(os.path.expanduser(bound.resource))


def retiring_words(bound: Bound) -> List[str]:
    """The RETIREMENTS keys the rendered replacement would spell: for each control it gives, its flag
    (``flag:NOUN.--FLAG``), its control (``param:NOUN.NAME``) and each value (``value:NOUN.NAME=VALUE``). A replacement
    that names a spelling which itself retires (git ``?type=log`` rendered ``--view log``) would teach the next retired
    word, so it is never written (manager, step 6)."""
    from reveal.cli.invocation import RETIREMENTS
    from reveal.cli.routing.canonical import _flag_value, _given_flags, _unread
    keys: List[str] = []
    for spec, flag in _given_flags(bound.parser, bound.adapter, bound.params):
        value = _flag_value(spec, _unread(bound.params, spec.name))
        values = value if isinstance(value, (list, tuple)) else [value]
        candidates = [f'flag:{bound.scheme}.{flag}', f'param:{bound.scheme}.{spec.name}',
                      *(f'value:{bound.scheme}.{spec.name}={item}' for item in values)]
        keys += [key for key in candidates if key in RETIREMENTS and key not in keys]
    return keys


def _parses(bound: Bound, rendered: str, subcommand: bool, other_words: Sequence[str]) -> object:
    """The noun parser's namespace for the rendered request's target and flags plus the example's other words."""
    argv = shlex.split(rendered)[1:]
    target_words = argv[1:] if subcommand else [bound.resource, *argv[1:]]
    return bound.parser.parse_args([*target_words, *other_words])


def render(uri: str, other_words: Sequence[str]) -> Tuple[str, str, bool]:
    """(the canonical CLI request for *uri*, its form, whether a subcommand rendering fell back) where *other_words* are
    the reveal command's other words (flags before and after the URI). Raises ``ValueError`` (``UnrenderableRequest``
    included) with the reason.

    The form (manager ruling, BACK-2726 step 2; D1): the subcommand (``canonical.render_request``) where the noun declares
    one and the target is a plain path, else the resource URI and flags (``canonical.render_uri_request``, the request
    note's own form). A subcommand rendering is kept only if it round-trips: the noun parser reads it back with the URI's
    resource as its target; otherwise the resource form is kept and counted."""
    from reveal.cli.routing.canonical import canonical_controls, render_request, render_uri_request
    from reveal.errors import RequestValidationError
    bound = bind_uri(uri)
    controls = canonical_controls(bound.parser, bound.adapter, bound.params, bound.walk_policy)
    flagged = {w[2:].partition('=')[0].replace('-', '_') for w in other_words if w.startswith('--')}
    both = sorted(flagged & set(controls))
    if both:
        raise _Left(f'{BOTH_SPELL} ({", ".join(both)})')
    retiring = retiring_words(bound)
    if retiring:
        raise _Left(f'{RETIRING_REPLACEMENT}: {", ".join(retiring)}')
    keywords = dict(parser=bound.parser, adapter=bound.adapter, walk_policy=bound.walk_policy,
                    presentation=not _typed_presentation(other_words))
    analysis_only = getattr(bound.adapter, 'ANALYSIS_ONLY', False)
    fell_back = False
    if not analysis_only and plain_path(bound):
        rendered = render_request('cli', bound.scheme, bound.resource or None, bound.params, **keywords)
        try:
            args = _parses(bound, rendered, True, other_words)
            if getattr(args, bound.adapter.RESOURCE_SPEC.name, None) == (bound.resource or None):
                return rendered, 'subcommand', False
        except (RequestValidationError, SystemExit, ValueError):
            pass
        fell_back = True
    rendered = render_uri_request('cli', bound.scheme, bound.resource, bound.params, **keywords)
    try:
        _parses(bound, rendered, analysis_only, other_words)
    except (RequestValidationError, SystemExit, ValueError) as exc:
        raise _Left(f'{DOES_NOT_PARSE}: {exc}') from None
    return rendered, 'subcommand' if analysis_only else 'resource', fell_back


class _Left(Exception):
    """An example the script leaves as written, with the reason."""


@dataclass
class Example:
    source: str
    line: str
    tokens: List[str]
    scheme: str = ''
    kind: str = 'none'  # 'rewrite' | 'left'
    reason: str = ''
    new_line: str = ''
    form: str = ''  # a rewrite's form: 'subcommand' | 'resource'
    origin: str = 'query'  # 'query': a retiring URI request; 'resource': an already-written resource line (step 7)
    fell_back: bool = False  # a subcommand rendering that did not round-trip: the resource form was kept
    physical: str = ''  # a continued command: its first physical line (stripped), which holds the URI word
    new_physical: str = ''  # ... and that line rewritten

    @property
    def key(self) -> str:
        """The text of the file's line that a rewrite replaces: the command, or a continued command's first line."""
        return self.physical or self.line

    @property
    def new_key(self) -> str:
        return self.new_physical or self.new_line


def _literal_spellings(word: str) -> List[str]:
    return [shlex.quote(word), f"'{word}'", f'"{word}"', word]


def _located(line: str, word: str) -> Optional[Tuple[int, str]]:
    """(offset, literal) of *word* as written in *line*: quoted or bare, as one shell word."""
    for literal in dict.fromkeys(_literal_spellings(word)):
        for match in re.finditer(re.escape(literal), line):
            start, end = match.span()
            if (start == 0 or line[start - 1].isspace()) and (end == len(line) or line[end].isspace()):
                return start, literal
    return None


def _continued_first_line(line: str, text: str) -> Optional[str]:
    """The first physical line (stripped, ending in its backslash) of the backslash-continued command *line*, which the
    extractor reads with each backslash-newline joined to a space; None when *line* is no such command of *text* (an
    argument quoted across lines keeps a newline in *line*)."""
    if '\n' in line:
        return None
    found = {raw.strip() for raw in text.split('\n')
             if raw.strip().endswith('\\') and line.startswith(raw.strip()[:-1])}
    return found.pop() if len(found) == 1 else None


def address_slots(uri: str) -> Optional[Dict[str, str]]:
    """{stand-in: placeholder} for the ``<placeholder>`` words in *uri*'s address part (before ``?``), the part the binder
    reads as an opaque resource name; {} when *uri* has none. None when *uri* holds a shell variable (rendering would
    quote it and stop the shell expanding it) or a placeholder in a query value (the noun binds and types values:
    ``limit=<N>``, a callee name), which are left for a hand edit."""
    address, _, query = uri.partition('?')
    if SHELL_VARIABLE.search(uri) or ANGLE_PLACEHOLDER.search(query):
        return None
    words = list(dict.fromkeys(ANGLE_PLACEHOLDER.findall(address)))
    return {SLOT.format(i): word for i, word in enumerate(words)}


def _filled(text: str, slots: Dict[str, str], back: bool = False) -> str:
    for slot, word in slots.items():
        text = text.replace(word, slot) if not back else text.replace(slot, word)
    return text


def resource_line_index(tokens: Sequence[str]) -> Optional[int]:
    """The index of the URI word when *tokens* is an already-written resource line: its first word that is not a flag is
    a URI to a known scheme that is not analysis-only and spells no query string (``retiring_uri_index`` reads the
    others). None otherwise."""
    from reveal.adapters.base import get_adapter_class
    words = [(i, w) for i, w in enumerate(tokens[1:], 1) if not w.startswith('-')]
    if not words or '://' not in words[0][1]:
        return None
    index, word = words[0]
    scheme, _, rest = word.partition('://')
    adapter = get_adapter_class(scheme.lower())
    if adapter is None or '?' in rest or getattr(adapter, 'ANALYSIS_ONLY', False):
        return None
    return index


def _plain_resource_line(tokens: Sequence[str], index: int) -> bool:
    """Whether a resource line is an example of the extra pass: a declared noun with a request note, a flag after the
    URI, and a resource the plain-path rule calls a plain path (an address, or a URI the binder refuses, is not)."""
    from reveal.cli.invocation import request_noted
    uri = tokens[index]
    if not request_noted(uri.partition('://')[0].lower()):
        return False
    if not any(w.startswith('-') for i, w in enumerate(_stage(tokens, 1), 1) if i != index):
        return False
    try:
        return plain_path(bind_uri(uri))
    except (ValueError, TypeError):
        return False


def classify(source: str, line: str, tokens: List[str], failing: bool, text: str,
             nouns: Optional[Sequence[str]] = None) -> Optional[Example]:
    """The plan for one documented command, or None when it is no retiring URI request. *nouns*: rewrite only these
    schemes' requests (the rest are left, counted)."""
    from reveal.cli.invocation import request_noted
    from scripts.check_retired_names import REPLACED_BY_CONTEXT
    index, origin = retiring_uri_index(tokens), 'query'
    if index is None:
        index, origin = resource_line_index(tokens), 'resource'
        if index is None or not _plain_resource_line(tokens, index):
            return None
    uri = tokens[index]
    example = Example(source, line, list(tokens), uri.partition('://')[0].lower(), origin=origin)

    def left(reason: str) -> Example:
        example.kind, example.reason = 'left', reason
        return example

    if failing:
        return left(SHOWN_FAILING)
    if REPLACED_BY_CONTEXT.search(line):
        return left(NAMES_DEPRECATED)
    if ' #' in line and URI_COMMENT.search(line.split(' #', 1)[1]):
        return left(SHOWS_THE_URI)
    if source.endswith('#embedded-md'):
        return left(EMBEDDED)
    if not request_noted(example.scheme):  # a twin: retiring_uri_index reads no scheme that neither notes nor retires
        return left(NO_REQUEST_NOTE_TWIN)
    slots = address_slots(uri)
    if slots is None:
        return left(PLACEHOLDER)
    if nouns is not None and example.scheme not in nouns:
        return left(OTHER_NOUN)
    physical = None
    if not any(raw.strip() == line for raw in text.split('\n')):
        physical = _continued_first_line(line, text)
        if physical is None:
            return left(NOT_ONE_LINE)
    stage = _stage(tokens, 1)
    if 'reveal' in tokens[len(stage) + 1:]:
        return left(SEVERAL_COMMANDS)
    others = [w for i, w in enumerate(stage, 1) if i != index]
    try:
        rendered, form, fell_back = render(_filled(uri, slots), others)
        if slots:  # each placeholder back in its word, the word quoted as the shell needs
            rendered = shlex.join(_filled(word, slots, back=True) for word in shlex.split(rendered))
    except _Left as exc:
        return left(str(exc))
    except ValueError as exc:  # UnrenderableRequest is a ValueError; the binder raises ValueError too
        from reveal.cli.routing.canonical import UnrenderableRequest
        prefix = UNRENDERABLE if isinstance(exc, UnrenderableRequest) else BINDER_REJECTS
        return left(f'{prefix}: {exc}')
    except TypeError as exc:
        return left(f'{BINDER_REJECTS}: {exc}')
    if origin == 'resource' and form != 'subcommand':
        return left(NO_ROUND_TRIP)
    first = line if physical is None else physical[:-1]  # the continued line without its backslash
    found = _located(first, uri)
    if found is None:
        return left(NOT_LOCATED if physical is None else NOT_ONE_LINE)
    start, literal = found
    new_first = first[:start] + rendered[len('reveal '):] + first[start + len(literal):]
    new_line = new_first + line[len(first):]
    # The rewrite changes the URI word only: the new command's words are the old ones with that word replaced.
    expected = [*tokens[:index], *shlex.split(rendered)[1:], *tokens[index + 1:]]
    if shlex.split(new_line, comments=True) != expected:
        return left(NOT_LOCATED)
    example.kind, example.new_line, example.form, example.fell_back = 'rewrite', new_line, form, fell_back
    if physical is not None:
        example.physical, example.new_physical = physical, new_first + '\\'
    return example


def documented_sources(docs: Path = DOCS) -> Dict[str, Path]:
    """docs-relative source name -> path, as the extractor names them (*docs*: a ``reveal/docs`` tree)."""
    return dict(_extractor_sources(docs))


def plan(sources: Optional[Sequence[str]] = None, nouns: Optional[Sequence[str]] = None,
         docs: Path = DOCS) -> Dict[str, List[Example]]:
    """source name -> the planned examples (retiring URI requests only), for *sources* (default: all); *nouns*:
    ``classify``."""
    texts = {name: path.read_text(encoding='utf-8') for name, path in documented_sources(docs).items()}
    out: Dict[str, List[Example]] = {name: [] for name in (sources if sources is not None else texts)}
    for source, line, tokens, failing in documented_commands(docs):
        base = source.removesuffix('#embedded-md')
        if base not in out:
            continue
        example = classify(source, line, list(tokens), failing, texts[base], nouns)
        if example is not None:
            out[base].append(example)
    for examples in out.values():  # lines are rewritten by text: a copy left anywhere keeps every copy
        kept = {e.key for e in examples if e.kind == 'left'}
        for e in examples:
            if e.kind == 'rewrite' and e.key in kept:
                e.kind, e.reason, e.new_line, e.new_physical = 'left', COPY_LEFT, '', ''
    return out


def prose_uri_count(text: str) -> Counter:
    """Query-string URI mentions outside fenced blocks (the report's prose column; never edited), by scheme."""
    unfenced = re.sub(r'^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*$', '', text, flags=re.M | re.S)
    return Counter(m.group(1) for m in PROSE_URI.finditer(unfenced))


def rewrite_text(text: str, examples: Sequence[Example]) -> Tuple[str, int]:
    """*text* with each planned rewrite applied to every line that is exactly its command, or a continued command's
    first line (indentation kept), inside the bash/sh/shell fences the extractor reads. A command left anywhere in the
    file (the doc shows that copy failing) is left everywhere: lines are matched by text."""
    kept = {e.key for e in examples if e.kind != 'rewrite'}
    swaps = {e.key: e.new_key for e in examples if e.kind == 'rewrite' and e.key not in kept}
    lines, done = text.split('\n'), 0
    shell = False
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped.startswith('```'):
            shell = not shell and stripped in ('```bash', '```sh', '```shell')
            continue
        if shell and stripped in swaps:
            lines[i] = raw[:len(raw) - len(raw.lstrip())] + swaps[stripped]
            done += 1
    return '\n'.join(lines), done


def expected_baseline(sources: Sequence[str], nouns: Optional[Sequence[str]] = None) -> Tuple[int, int]:
    """(now, after) of the doc URI-request ratchet if *sources* were written (computed on a scratch copy)."""
    import shutil
    import tempfile
    now = len(documented_uri_requests(DOCS))
    planned = plan(sources, nouns)
    with tempfile.TemporaryDirectory() as tmp:
        docs = Path(tmp) / 'reveal' / 'docs'
        shutil.copytree(DOCS, docs)
        shutil.copy(ROOT / 'README.md', Path(tmp) / 'README.md')
        for name, examples in planned.items():
            path = docs / name
            text, _ = rewrite_text(path.read_text(encoding='utf-8'), examples)
            path.write_text(text, encoding='utf-8')
        after = len(documented_uri_requests(docs))
    return now, after


def _source_name(arg: str, sources: Dict[str, Path]) -> Optional[str]:
    resolved = Path(arg).resolve()
    return next((name for name, path in sources.items() if path.resolve() == resolved), None)


def _summary(examples: Sequence[Example]) -> Dict[str, object]:
    reasons = Counter(e.reason.split(':')[0] for e in examples if e.kind == 'left')
    return {'found': len(examples), 'rewritten': sum(e.kind == 'rewrite' for e in examples),
            'left': sum(e.kind == 'left' for e in examples), 'left_by_reason': dict(reasons.most_common()),
            'by_scheme': dict(Counter(e.scheme for e in examples).most_common()),
            'forms': dict(Counter(e.form for e in examples if e.kind == 'rewrite').most_common()),
            'resource_lines': sum(e.kind == 'rewrite' and e.origin == 'resource' for e in examples),
            'round_trip_fallbacks': sum(e.kind == 'rewrite' and e.fell_back for e in examples)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='dry run: report, write nothing')
    mode.add_argument('--write', action='store_true', help='rewrite the named docs in place')
    parser.add_argument('--show', action='store_true', help='print each rewrite and each left example with its reason')
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    parser.add_argument('--baseline', action='store_true',
                        help='also compute the doc URI-request ratchet after writing the named docs (scratch copy)')
    parser.add_argument('--noun', action='append', dest='nouns', metavar='SCHEME',
                        help='rewrite only this scheme\'s requests (repeatable); the others are left and counted')
    parser.add_argument('docs', nargs='*', help='doc paths (default with --check: every extractor source)')
    args = parser.parse_args(argv)
    sources = documented_sources()
    if args.write and not args.docs:
        parser.error('--write needs the doc paths to rewrite')
    unread = [d for d in args.docs if _source_name(d, sources) is None]
    names = [n for n in (_source_name(d, sources) for d in args.docs) if n] if args.docs else list(sources)
    planned = plan(names, args.nouns)
    report = {name: {**_summary(examples), 'prose': sum(prose_uri_count(sources[name].read_text(encoding='utf-8')).values())}
              for name, examples in planned.items()}
    if args.write:
        for name, examples in planned.items():
            path = sources[name]
            text, done = rewrite_text(path.read_text(encoding='utf-8'), examples)
            if done:
                path.write_text(text, encoding='utf-8', newline='')
            report[name]['lines_written'] = done
    baseline = expected_baseline(names, args.nouns) if args.baseline else None
    if args.format == 'json':
        detail = {name: [{'line': e.line, 'kind': e.kind, 'reason': e.reason, 'new_line': e.new_line, 'scheme': e.scheme,
                          'form': e.form, 'fell_back': e.fell_back, 'origin': e.origin, 'physical': e.physical,
                          'new_physical': e.new_physical}
                         for e in examples] for name, examples in planned.items()} if args.show else None
        print(json.dumps({'files': report, 'not_extractor_sources': unread, 'detail': detail,
                          'baseline': None if baseline is None else {'now': baseline[0], 'after': baseline[1]}},
                         indent=2))
        return 0
    for doc in unread:
        print(f'{doc}: not a source the executable-docs extractor reads; left as written')
    total = Counter()
    for name, row in report.items():
        if not row['found'] and not row['prose']:
            continue
        total.update({k: row[k] for k in ('found', 'rewritten', 'left', 'prose')})
        reasons = '; '.join(f'{n} {r}' for r, n in row['left_by_reason'].items())
        forms = ', '.join(f'{n} {form}' for form, n in row['forms'].items())
        fallbacks = f", {row['round_trip_fallbacks']} kept the resource form (no round trip)" \
            if row['round_trip_fallbacks'] else ''
        fallbacks += f", {row['resource_lines']} from resource lines" if row['resource_lines'] else ''
        print(f"{name}: found {row['found']}, {'written' if args.write else 'rewritten'} {row['rewritten']}"
              f"{' (' + forms + fallbacks + ')' if forms else ''}, left {row['left']}{' (' + reasons + ')' if reasons else ''}; prose mentions {row['prose']}")
        if args.show:
            for e in planned[name]:
                if e.kind == 'rewrite':
                    print(f'    - {e.line}\n    + {e.new_line}')
                else:
                    print(f'    = {e.line}\n      left: {e.reason}')
    print(f"total: found {total['found']}, rewritten {total['rewritten']}, left {total['left']}, "
          f"prose mentions {total['prose']}")
    if baseline is not None:
        print(f'doc URI-request ratchet: {baseline[0]} now, {baseline[1]} after writing these docs')
    return 0


if __name__ == '__main__':
    sys.exit(main())
