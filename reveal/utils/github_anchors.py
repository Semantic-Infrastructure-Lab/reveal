"""GitHub-flavoured markdown anchors: the one place a heading becomes a `#fragment`.

`--links` and rule L001 both ask whether `#some-anchor` resolves, and they answered from two
slugifiers that had drifted apart (BACK-1232 fixed hyphen runs in one, BACK-1901). A link that works
on GitHub must verify here, so both call this module, which follows GitHub's own rules:

- the slug comes from the heading's rendered text: emphasis markers, link syntax and inline HTML
  tags are gone, code-span text stays literal (`Quectel_BG77.cs` keeps its underscore);
- lowercase, drop everything except word characters, hyphens and spaces, then turn EACH space
  into its own hyphen. Nothing is collapsed or trimmed, so `Features ✨` is `features-`;
- a later heading with the same slug gets `-1`, `-2`, ... in document order;
- an explicit `<a id="x">` / `<a name="x">` / `id="x"` in the file is an anchor too.
"""
import re
from typing import Dict, Iterable, List

from .lines import split_lines

_LINK_OR_IMAGE = re.compile(r'!?\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])')
_CODE_SPAN = re.compile(r'(`+)(.+?)\1')
# `_x_` / `__x__` is emphasis only at a word boundary: `snake_case_word` keeps its underscores.
_UNDERSCORE_EMPHASIS = re.compile(r'(?<!\w)(_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)')
_HTML_TAG = re.compile(r'</?[A-Za-z][^>]*>')
_NOT_IN_SLUG = re.compile(r'[^\w\- ]')

_FENCE = re.compile(r'^\s*(```|~~~)')
_TAG = re.compile(r'<(?P<tag>[A-Za-z][A-Za-z0-9]*)\b(?P<attrs>[^>]*)>')
_ATTR = {
    'id': re.compile(r'\sid\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.IGNORECASE),
    'name': re.compile(r'\sname\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.IGNORECASE),
}


def _rendered_text(heading: str) -> str:
    """The heading as GitHub reads it for the slug: markup removed, code-span text kept."""
    text = _LINK_OR_IMAGE.sub(r'\1', heading.strip())
    parts = _CODE_SPAN.split(text)
    # re.split with two groups yields: text, fence, code, text, fence, code, ...
    out: List[str] = []
    for index in range(0, len(parts), 3):
        prose = _HTML_TAG.sub('', parts[index])
        out.append(_UNDERSCORE_EMPHASIS.sub(r'\2', prose))
        if index + 2 < len(parts):
            out.append(parts[index + 2])
    return ''.join(out)


def heading_slug(heading: str) -> str:
    """The anchor GitHub gives one heading on its own (no duplicate suffix)."""
    return _NOT_IN_SLUG.sub('', _rendered_text(heading).lower()).replace(' ', '-')


def heading_anchors(headings: Iterable[str]) -> List[str]:
    """Anchors of *headings* in document order, duplicates suffixed as GitHub does.

    A heading whose text leaves no slug (``***``) is not an anchor.
    """
    seen: Dict[str, int] = {}
    anchors: List[str] = []
    for heading in headings:
        base = heading_slug(heading)
        if not base:
            continue
        slug = base
        while slug in seen:
            seen[base] += 1
            slug = f'{base}-{seen[base]}'
        seen[slug] = 0
        anchors.append(slug)
    return anchors


def html_anchor_ids(content: str) -> List[str]:
    """Explicit anchors written as HTML: ``id`` on any tag, ``name`` on ``<a>``.

    Fenced code blocks are skipped. A link such as ``#rtc-history`` resolves on GitHub to
    ``<a id="rtc-history">`` even though no heading has that slug.
    """
    ids: List[str] = []
    in_fence = False
    for line in split_lines(content):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or '<' not in line:
            continue
        for tag in _TAG.finditer(line):
            wanted = ('id', 'name') if tag.group('tag').lower() == 'a' else ('id',)
            found = [(m.start(), m.group(1) or m.group(2))
                     for key in wanted for m in [_ATTR[key].search(tag.group('attrs'))] if m]
            ids.extend(value for _, value in sorted(found) if value not in ids)
    return ids
