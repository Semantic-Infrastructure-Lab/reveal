#!/usr/bin/env python3
"""Rewrite the documented URI-request examples as the canonical request the request note recommends (BACK-2726).

A documented command whose first word is a retiring URI request (an analysis-only scheme, or any URI spelling a query
string; BACK-2716) is rewritten as the executable canonical request rendered from the bound request by
``reveal.cli.routing.canonical.render_uri_request``, the request note's own renderer: ``reveal NOUN TARGET --flags``
for an analysis-only scheme, the resource URI followed by flags for a resource (D20). Nothing here parses a URI or
finds an example on its own:

  examples   ``tests/test_example_recipes_run.py`` ``_documented_commands`` (the executable-docs gate's extractor:
             fenced bash/sh/shell blocks and embedded Markdown tables), and its ``_documented_uri_requests`` predicate
             for what counts as a retiring URI request (the ``.github/doc_uri_requests_baseline.json`` ratchet);
  binding    the same steps ``reveal.api._note_uri_request`` takes: ``split_respect_gitignore``, then the binder's
             ``prepare_declared_params(..., 'uri')`` over the noun's declarations;
  rendering  ``render_uri_request(form='cli', ...)``, with the request's typed ``--format``/``--output`` kept as the note
             keeps it (``presentation=False``);
  context    ``scripts/check_retired_names.py`` ``REPLACED_BY_CONTEXT``: a command line that says its spelling is
             deprecated (an inline ``# deprecated`` comment) is left, as prose naming a retired spelling is.

Only the URI word changes: words before it, flags after it (BACK-2673: flags after a URI are the subcommand's flags),
pipes and comments stay as written. An example is left, with the reason counted, when the doc shows it failing, it names
its spelling as deprecated, it is not one line of the file, a control it gives has no flag (``UnrenderableRequest``),
the binder rejects it, a flag after the URI gives a control the URI gives too, the rendered line does not parse with
the noun's parser, or its scheme says no request note (a retired twin with its own ``scheme:`` row, or a noun with no
declared subcommand yet). Prose is never edited: inline backtick commands and other URI mentions outside executable
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
import re
import shlex
import sys
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
for _path in (ROOT, ROOT / 'tests', ROOT / 'scripts'):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

DOCS = ROOT / 'reveal' / 'docs'

# Why an example is left as written; every left example carries exactly one.
SHOWN_FAILING = 'the doc shows it failing'
NAMES_DEPRECATED = 'its line names the spelling as deprecated'
SHOWS_THE_URI = 'its comment presents it as the URI spelling of a neighbouring line: by hand'
OTHER_NOUN = 'its noun is outside --noun'
NOT_ONE_LINE = 'not one line of the file (a continuation or multi-line argument)'
NOT_LOCATED = 'the URI word is not spelled as one quoted or bare word'
PLACEHOLDER = 'a <placeholder> or $VARIABLE in the URI'
NO_REQUEST_NOTE_TWIN = 'retired twin scheme: its own scheme: row is the note, not a request note'
NO_REQUEST_NOTE_UNDECLARED = 'no declared subcommand yet: the URI says no request note'
UNRENDERABLE = 'no canonical form'  # + the renderer's reason
BINDER_REJECTS = 'the binder rejects the request'  # + the binder's message
BOTH_SPELL = 'a flag after the URI gives a control the URI gives too'
DOES_NOT_PARSE = 'the rendered line does not parse with the noun parser'  # + the parser's message
EMBEDDED = 'an embedded Markdown table cell: by hand'
COPY_LEFT = 'a copy of this line elsewhere in the file is left (lines are rewritten by text)'
SEVERAL_COMMANDS = 'another reveal command follows on the line (the extractor reads the first): by hand'

# A comment that presents the example as the other spelling of a neighbouring command ("# the same answer as a URI"):
# rewritten, it would repeat that command under a false comment.
URI_COMMENT = re.compile(r'\bURI\b|\bsame (?:answer|request|result)\b|query[- ]param', re.IGNORECASE)
# The extractor's placeholder shape (tests/test_example_recipes_run.py ``_named_fixture_skip``), and shell variables
# ($file, ${x}, $(cmd)); a regex anchor (name~=Manager$) is a value.
PLACEHOLDER_WORD = re.compile(r'<[A-Za-z_-]+>|\$[A-Za-z_{(]')
PROSE_URI = re.compile(r'\b([a-z]+)://[^\s`\'")\]|]*\?[^\s`\'")\]|]*')
_SHELL_WORDS = {'|', '||', '&&', ';', '>', '>>', '2>&1', '2>/dev/null'}


def extractor():
    """The executable-docs gate's extractor module (tests/test_example_recipes_run.py)."""
    import test_example_recipes_run
    return test_example_recipes_run


def retiring_uri_index(tokens: Sequence[str]) -> Optional[int]:
    """The index of the URI word when *tokens* is a retiring URI request as ``_documented_uri_requests`` counts one:
    the first word that is not a flag names a scheme whose adapter is analysis-only, or it spells a query string."""
    from reveal.adapters.base import get_adapter_class
    words = [(i, w) for i, w in enumerate(tokens[1:], 1) if not w.startswith('-')]
    if not words or '://' not in words[0][1]:
        return None
    index, word = words[0]
    scheme, _, rest = word.partition('://')
    adapter = get_adapter_class(scheme.lower())
    if adapter is not None and (getattr(adapter, 'ANALYSIS_ONLY', False) or '?' in rest):
        return index
    return None


@dataclass
class Bound:
    scheme: str
    resource: str
    params: object
    walk_policy: Optional[bool]
    adapter: object
    parser: object


def bind_uri(uri: str) -> Bound:
    """The request a URI binds, by the steps ``reveal.api._note_uri_request`` takes (the walk policy split off first)."""
    from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
    from reveal.utils.gitignore import split_respect_gitignore
    from reveal.utils.query_binding import prepare_declared_params
    scheme, _, rest = uri.partition('://')
    split, walk_policy = split_respect_gitignore(rest)
    resource, _, query = split.partition('?')
    adapter = declared_adapter_class(scheme)
    params = prepare_declared_params(adapter.PARAM_SPECS, query, 'uri')
    parser = create_declared_parser(scheme)
    parser.raise_usage_errors = True
    return Bound(scheme, resource, params, walk_policy, adapter, parser)


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


def render(uri: str, other_words: Sequence[str]) -> str:
    """The canonical CLI request for *uri*, as the request note renders it; *other_words* are the reveal command's other
    words (flags before and after the URI). Raises ``ValueError`` (``UnrenderableRequest`` included) with the reason."""
    from reveal.cli.routing.canonical import canonical_controls, render_uri_request
    from reveal.errors import RequestValidationError
    bound = bind_uri(uri)
    rendered = render_uri_request('cli', bound.scheme, bound.resource, bound.params, parser=bound.parser,
                                  adapter=bound.adapter, walk_policy=bound.walk_policy,
                                  presentation=not _typed_presentation(other_words))
    controls = canonical_controls(bound.parser, bound.adapter, bound.params, bound.walk_policy)
    flagged = {w[2:].partition('=')[0].replace('-', '_') for w in other_words if w.startswith('--')}
    both = sorted(flagged & set(controls))
    if both:
        raise _Left(f'{BOTH_SPELL} ({", ".join(both)})')
    argv = shlex.split(rendered)[1:]
    target_words = argv[1:] if getattr(bound.adapter, 'ANALYSIS_ONLY', False) else [bound.resource, *argv[1:]]
    try:
        bound.parser.parse_args([*target_words, *other_words])
    except (RequestValidationError, SystemExit, ValueError) as exc:
        raise _Left(f'{DOES_NOT_PARSE}: {exc}') from None
    return rendered


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


def classify(source: str, line: str, tokens: List[str], failing: bool, text: str,
             nouns: Optional[Sequence[str]] = None) -> Optional[Example]:
    """The plan for one documented command, or None when it is no retiring URI request. *nouns*: rewrite only these
    schemes' requests (the rest are left, counted)."""
    from reveal.cli.invocation import RETIREMENTS, request_noted
    from check_retired_names import REPLACED_BY_CONTEXT
    index = retiring_uri_index(tokens)
    if index is None:
        return None
    uri = tokens[index]
    example = Example(source, line, list(tokens), uri.partition('://')[0].lower())

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
    if not request_noted(example.scheme):
        twin = f'scheme:{example.scheme}' in RETIREMENTS
        return left(NO_REQUEST_NOTE_TWIN if twin else NO_REQUEST_NOTE_UNDECLARED)
    if PLACEHOLDER_WORD.search(uri):
        return left(PLACEHOLDER)
    if nouns is not None and example.scheme not in nouns:
        return left(OTHER_NOUN)
    if '\n' in line or not any(raw.strip() == line for raw in text.split('\n')):
        return left(NOT_ONE_LINE)
    stage = _stage(tokens, 1)
    if 'reveal' in tokens[len(stage) + 1:]:
        return left(SEVERAL_COMMANDS)
    others = [w for i, w in enumerate(stage, 1) if i != index]
    try:
        rendered = render(uri, others)
    except _Left as exc:
        return left(str(exc))
    except ValueError as exc:  # UnrenderableRequest is a ValueError; the binder raises ValueError too
        from reveal.cli.routing.canonical import UnrenderableRequest
        prefix = UNRENDERABLE if isinstance(exc, UnrenderableRequest) else BINDER_REJECTS
        return left(f'{prefix}: {exc}')
    except TypeError as exc:
        return left(f'{BINDER_REJECTS}: {exc}')
    found = _located(line, uri)
    if found is None:
        return left(NOT_LOCATED)
    start, literal = found
    new_line = line[:start] + rendered[len('reveal '):] + line[start + len(literal):]
    # The rewrite changes the URI word only: the new line's words are the old ones with that word replaced.
    expected = [*tokens[:index], *shlex.split(rendered)[1:], *tokens[index + 1:]]
    if shlex.split(new_line, comments=True) != expected:
        return left(NOT_LOCATED)
    example.kind, example.new_line = 'rewrite', new_line
    return example


def documented_sources(docs: Path = DOCS) -> Dict[str, Path]:
    """docs-relative source name -> path, as the extractor names them (*docs*: a ``reveal/docs`` tree)."""
    return dict(extractor()._documented_sources(docs))


def plan(sources: Optional[Sequence[str]] = None, nouns: Optional[Sequence[str]] = None,
         docs: Path = DOCS) -> Dict[str, List[Example]]:
    """source name -> the planned examples (retiring URI requests only), for *sources* (default: all); *nouns*:
    ``classify``."""
    texts = {name: path.read_text(encoding='utf-8') for name, path in documented_sources(docs).items()}
    out: Dict[str, List[Example]] = {name: [] for name in (sources if sources is not None else texts)}
    for source, line, tokens, failing in extractor()._documented_commands(docs):
        base = source.removesuffix('#embedded-md')
        if base not in out:
            continue
        example = classify(source, line, list(tokens), failing, texts[base], nouns)
        if example is not None:
            out[base].append(example)
    for examples in out.values():  # lines are rewritten by text: a copy left anywhere keeps every copy
        kept = {e.line for e in examples if e.kind == 'left'}
        for e in examples:
            if e.kind == 'rewrite' and e.line in kept:
                e.kind, e.reason, e.new_line = 'left', COPY_LEFT, ''
    return out


def prose_uri_count(text: str) -> Counter:
    """Query-string URI mentions outside fenced blocks (the report's prose column; never edited), by scheme."""
    unfenced = re.sub(r'^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*$', '', text, flags=re.M | re.S)
    return Counter(m.group(1) for m in PROSE_URI.finditer(unfenced))


def rewrite_text(text: str, examples: Sequence[Example]) -> Tuple[str, int]:
    """*text* with each planned rewrite applied to every line that is exactly its command (indentation kept), inside the
    bash/sh/shell fences the extractor reads. A command left anywhere in the file (the doc shows that copy failing) is
    left everywhere: lines are matched by text."""
    kept = {e.line for e in examples if e.kind != 'rewrite'}
    swaps = {e.line: e.new_line for e in examples if e.kind == 'rewrite' and e.line not in kept}
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


@contextmanager
def documented_at(docs: Path) -> Iterator[None]:
    """The extractor reading *docs* instead of the shipped tree (for the expected baseline after a write)."""
    module = extractor()
    original = module._documented_commands
    module._documented_commands = lambda _docs=None: original(docs)
    try:
        yield
    finally:
        module._documented_commands = original


def expected_baseline(sources: Sequence[str], nouns: Optional[Sequence[str]] = None) -> Tuple[int, int]:
    """(now, after) of the doc URI-request ratchet if *sources* were written (computed on a scratch copy)."""
    import shutil
    import tempfile
    module = extractor()
    now = len(module._documented_uri_requests())
    planned = plan(sources, nouns)
    with tempfile.TemporaryDirectory() as tmp:
        docs = Path(tmp) / 'reveal' / 'docs'
        shutil.copytree(DOCS, docs)
        shutil.copy(ROOT / 'README.md', Path(tmp) / 'README.md')
        for name, examples in planned.items():
            path = docs / name
            text, _ = rewrite_text(path.read_text(encoding='utf-8'), examples)
            path.write_text(text, encoding='utf-8')
        with documented_at(docs):
            after = len(module._documented_uri_requests())
    return now, after


def _source_name(arg: str, sources: Dict[str, Path]) -> Optional[str]:
    resolved = Path(arg).resolve()
    return next((name for name, path in sources.items() if path.resolve() == resolved), None)


def _summary(examples: Sequence[Example]) -> Dict[str, object]:
    reasons = Counter(e.reason.split(':')[0] for e in examples if e.kind == 'left')
    return {'found': len(examples), 'rewritten': sum(e.kind == 'rewrite' for e in examples),
            'left': sum(e.kind == 'left' for e in examples), 'left_by_reason': dict(reasons.most_common()),
            'by_scheme': dict(Counter(e.scheme for e in examples).most_common())}


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
        detail = {name: [{'line': e.line, 'kind': e.kind, 'reason': e.reason, 'new_line': e.new_line, 'scheme': e.scheme}
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
        print(f"{name}: found {row['found']}, {'written' if args.write else 'rewritten'} {row['rewritten']}, "
              f"left {row['left']}{' (' + reasons + ')' if reasons else ''}; prose mentions {row['prose']}")
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
