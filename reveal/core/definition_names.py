"""How a queried name matches a definition's name -- one rule for every lookup.

C++ out-of-line definitions carry their qualified name (`FileAccess::get_bytes`,
`ns::Outer::f`); every other language stores the bare name (Lua `M.foo` is
`foo`, Ruby `def self.foo` is `foo`). A query names such a definition by its
full name or by any trailing `::` segments, so `get_bytes`,
`FileAccess::get_bytes` and `ns::FileAccess::get_bytes` all find it.

BACK-1400: element extraction, `calls://?callees=` and `trace://` each matched
the stored name exactly, so `reveal io.cpp get_bytes`, `?callees=get_bytes`
and `trace --from get_bytes` all answered "not found" while
`calls://?target=get_bytes` (which bare-names call sites) found every caller.
"""

from typing import Optional, Tuple


def name_matches(definition_name: Optional[str], wanted: str) -> bool:
    """`wanted` names this definition: exactly, or as its trailing `::` segments."""
    if not definition_name:
        return False
    return definition_name == wanted or definition_name.endswith('::' + wanted)


def lookup_keys(definition_name: str) -> Tuple[str, ...]:
    """Index keys for a definition in a name -> definitions map: its full name,
    plus its bare last segment when qualified, so a bare call or query finds it.
    (Middle segments, `Outer::f` for `ns::Outer::f`, match through
    name_matches but are not keyed.)"""
    if '::' not in definition_name:
        return (definition_name,)
    return (definition_name, definition_name.rsplit('::', 1)[1])
