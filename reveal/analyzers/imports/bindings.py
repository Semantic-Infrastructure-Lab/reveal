"""What each import of a file binds a local name to, read from the resolved import analysis.

A consumer that looks a use up by name -- calls' callee resolution (BACK-2553) -- asks here
instead of resolving imports itself: the target file is the one the resolution pass found
(``ImportStatement.resolved_path``), and "external" is the extractor's verdict that pass
recorded (``ImportStatement.intra_verdict``, BACK-2550), so the answer is the one imports://
gives for the same statement.
"""

from typing import Dict, Iterable, NamedTuple, Optional

from .types import ImportStatement
from .unused import bound_names


class Binding(NamedTuple):
    """What an import binds a local name to."""
    target: Optional[str]   # the file the import resolved to
    external: bool          # no file, and the extractor says the import is outside the tree


def file_bindings(imports: Iterable[ImportStatement]) -> Dict[str, Binding]:
    """Local name -> binding, from one file's resolved import statements. A name is external only
    when every statement that binds it is; the unknown verdict (None) is not external."""
    bindings: Dict[str, Binding] = {}
    for stmt in imports:
        target = str(stmt.resolved_path) if stmt.resolved_path else None
        external = target is None and stmt.intra_verdict is False
        for name in bound_names(stmt):
            seen = bindings.get(name)
            bindings[name] = (Binding(target, external) if seen is None else
                              Binding(seen.target or target, seen.external and external))
    return bindings
