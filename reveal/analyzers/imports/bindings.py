"""What each import of a file binds a local name to, read from the resolved import analysis.

A consumer that looks a use up by name -- calls' callee resolution (BACK-2553) -- asks here
instead of resolving imports itself: the target file is the one the resolution pass found
(``ImportStatement.resolved_path``), and "external" is the extractor's verdict that pass
recorded (``ImportStatement.intra_verdict``, BACK-2550), so the answer is the one imports://
gives for the same statement.
"""

from typing import Dict, Iterable, NamedTuple, Optional

from .types import ImportStatement
from .unused import binds_reliably, bound_names


class Binding(NamedTuple):
    """What an import binds a local name to."""
    target: Optional[str]   # the file the import resolved to
    external: bool          # no file, and the extractor says the import is outside the tree


def file_bindings(imports: Iterable[ImportStatement]) -> Dict[str, Binding]:
    """Local name -> binding, from one file's resolved import statements. A name is external only
    when every statement that binds it is, and names a file only when they all name the same one;
    the unknown verdict (None) is not external, and neither
    is a bare import whose bound name is a guess (``binds_reliably``: C ``#include <array>`` binds
    no ``array``). Such an import still names its file when it resolved in-tree (Zig
    ``const config = @import("config.zig")``), which only ever narrows candidates."""
    bindings: Dict[str, Binding] = {}
    for stmt in imports:
        target = str(stmt.resolved_path) if stmt.resolved_path else None
        external = target is None and stmt.intra_verdict is False and binds_reliably(stmt)
        for name in bound_names(stmt):
            seen = bindings.get(name)
            # Several imports binding one name (Java `import org.a.X` and `import org.b.Y` both
            # bind the guess `org`) name a file only when they agree on it.
            bindings[name] = (Binding(target, external) if seen is None else
                              Binding(seen.target if seen.target == target else None,
                                      seen.external and external))
    return bindings
