"""Java `method_invocation` callee naming (shared by analyzer and nav)."""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from .generic import CHAIN_COLLAPSE, CHAIN_FULL, subtree_contains_call


def method_invocation(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """Java method_invocation: `[object? . name argument_list]` -> `object.name`.

    child(0) is only the *object* (`Files`, `path`), so the generic fallback
    dropped the method name (BACK-416, BACK-734). Emits the receiver-qualified
    callee (`Files.createDirectories`) so the taxonomy and calls:// see the method
    name. Chained calls (`a.b().c()`) whose object is itself a call collapse to
    `.name` under the nav policy (BACK-415); the analyzer index keeps the object text.
    """
    # Named fields, not positions: explicit type arguments (`svc.<T>run(x)`) put a
    # type_arguments node between the '.' and the name, which defeated positional
    # matching (BACK-1279: the nav-only form lost the receiver on these).
    name_node = node.child_by_field_name('name')
    if name_node is None:
        return None
    name = get_text(name_node).strip()
    obj_node = node.child_by_field_name('object')
    if obj_node is None:
        return name or None
    if (
        chain_receiver == CHAIN_COLLAPSE
        and call_node_types
        and subtree_contains_call(obj_node, call_node_types)
    ):
        return f".{name}" if name else None
    obj_text = get_text(obj_node).strip()
    if obj_text and name:
        return f"{obj_text}.{name}"
    return name or None
