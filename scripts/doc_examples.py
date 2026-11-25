"""The documented reveal commands of the shipped docs, and which of them teach a retiring URI request (BACK-2726).

One extractor for two readers: the executable-docs gate (``tests/test_example_recipes_run.py``: the named-fixture run,
the discovery run and the ``.github/doc_uri_requests_baseline.json`` ratchet) and the guide-migration script
(``scripts/migrate_doc_uri_examples.py``). Moved here unchanged from the gate (BACK-1365, BACK-2444, BACK-2449, BACK-2716).

  documented_sources(docs)      the docs the gate reads, by docs-relative name
  documented_commands(docs)     (source, text, tokens, shown failing) per command in a bash/sh/shell fence or an
                                embedded Markdown table
  retiring_uri_index(tokens)    the URI word of a command that is a retiring URI request, else None
  documented_uri_requests(docs) the distinct commands that teach one (the ratchet's count)
"""
import os
import re
import shlex
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Set, Tuple


def shell_reveal_commands(block: str) -> Iterator[Tuple[str, List[str]]]:
    """Keep backslash continuations and quoted multiline arguments together."""
    pending = ''
    for line in block.replace('\\\n', ' ').splitlines():
        if not pending and not line.strip().startswith('reveal '):
            continue
        pending = pending + '\n' + line if pending else line.strip()
        try:
            tokens = shlex.split(pending, comments=True)
        except ValueError:
            continue  # an open quote can legally continue onto the next line
        yield pending, tokens
        pending = ''
    assert not pending, f'Unterminated documented command: {pending}'


# A command the doc itself shows failing: `# not valid` beside it, or its `# Error:` output below.
DOCUMENTED_FAILURE = re.compile(r'#.*\b(not valid|invalid)\b|#\s*Error\b', re.IGNORECASE)


def documented_sources(docs: Path) -> Iterator[Tuple[str, Path]]:
    """Canonical source inventory; inventory is broader than qualified execution."""
    sources = [docs / 'AGENT_HELP.md', *sorted((docs / 'guides').glob('*.md')),
               docs.parent.parent / 'README.md', *sorted((docs / 'adapters').glob('*.md')),
               *(docs / name for name in ('QUICK_START.md', 'WHY_REVEAL.md', 'INDEX.md'))]
    for source in sources:
        if source.is_file():
            yield os.path.relpath(source, docs).replace(os.sep, '/'), source


def embedded_markdown_commands(text: str) -> Iterator[Tuple[str, List[str]]]:
    """Inventory single-backtick commands in embedded Markdown tables/lists only."""
    for fence, kind, block in re.findall(r'^(`{3,}|~{3,})([^\n]*)\n(.*?)^\1[ \t]*$', text, re.M | re.S):
        if kind not in ('md', 'markdown'):
            continue
        for line in block.split('\n'):
            if re.match(r'\s*(?:\||(?:\d+[.)]|[-+*])\s+)', line):
                for command in re.findall(r'(?<!`)`([^`\n]+)`(?!`)', line):
                    for command_text, tokens in shell_reveal_commands(command):
                        if len(tokens) > 1:
                            yield command_text, tokens


def default_docs() -> Path:
    import reveal
    return Path(reveal.__file__).parent / 'docs'


def documented_commands(docs: Optional[Path] = None) -> Iterator[Tuple[str, str, List[str], bool]]:
    """(docs-relative source, text, tokens, shown failing) per documented command."""
    docs = docs or default_docs()
    embedded = []
    for source_name, source in documented_sources(docs):
        text = source.read_text(encoding='utf-8')
        for block in re.findall(r'```(?:bash|sh|shell)\n(.*?)```', text, re.S):
            for line, tokens in shell_reveal_commands(block):
                if tokens:
                    after = block.split(line, 1)[-1].lstrip('\n').split('\n', 1)[0]
                    failing = bool(DOCUMENTED_FAILURE.search(line) or DOCUMENTED_FAILURE.match(after))
                    yield source_name, line, tokens, failing
        embedded.extend((source_name + '#embedded-md', line, tokens, bool(DOCUMENTED_FAILURE.search(line)))
                        for line, tokens in embedded_markdown_commands(text) if tokens)
    # Keep every existing shell occurrence first: an unqualified embedded copy must
    # never shadow a later shell example when named fixtures deduplicate commands.
    yield from embedded


def retiring_uri_index(tokens: Sequence[str]) -> Optional[int]:
    """The index of the URI word when *tokens* is a command whose first word that is not a flag is a URI request that
    retires: an analysis-only scheme, or any URI spelling a query string (BACK-2716), of a scheme that retires: it says
    the request note (``request_noted``) or is a retired twin whose own ``scheme:`` row is its note. An ops scheme says
    neither and never retires (D13), so its query string is no retiring request. None otherwise."""
    from reveal.adapters.base import get_adapter_class
    from reveal.cli.invocation import RETIREMENTS, request_noted
    words = [(i, w) for i, w in enumerate(tokens[1:], 1) if not w.startswith('-')]
    if not words or '://' not in words[0][1]:
        return None
    index, word = words[0]
    scheme, _, rest = word.partition('://')
    scheme = scheme.lower()
    adapter = get_adapter_class(scheme)
    if adapter is None or not (request_noted(scheme) or f'scheme:{scheme}' in RETIREMENTS):
        return None
    if getattr(adapter, 'ANALYSIS_ONLY', False) or '?' in rest:
        return index
    return None


def documented_uri_requests(docs: Optional[Path] = None) -> Set[str]:
    """The distinct documented commands whose first word is a URI request that retires (``retiring_uri_index``)."""
    return {shlex.join(tokens) for _source, _line, tokens, _failing in documented_commands(docs)
            if retiring_uri_index(tokens) is not None}
