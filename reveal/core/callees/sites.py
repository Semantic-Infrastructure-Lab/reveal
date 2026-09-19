"""One record per call site, for shapes where a call is spread across sibling nodes.

Node-kind-level shapes (`KIND_EXTRACTORS`) name a call from one node. Walker-level
shapes -- GDScript `attribute_call`, Dart selectors, Zig `SuffixExpr` -- keep the
receiver in *preceding siblings*, so a single node cannot name itself. The enumerator
for each shape yields `CallSite`s once; the analyzer and nav paths then differ only in
how they *project* a site (BACK-1309):

    analyzer  ->  `site.qualified`   full receiver text, one name per call node
    nav       ->  `site.dotted`      dotted-identifier receiver only; a call on the result
                                     of a previous call is `.member` (chain collapse)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CallSite:
    node: Any          # the node that holds the call's own arguments (line, first arg)
    member: str        # the called name, e.g. `size` in `x.size()`
    receiver: str      # full source text before `.member` (analyzer form), '' if none
    dotted: str        # dotted-identifier receiver with `.member` (nav form)
    args: Any = None   # the argument-list node when it is not `node` itself

    @property
    def arg_node(self) -> Any:
        return self.args if self.args is not None else self.node

    @property
    def qualified(self) -> str:
        """Analyzer projection: `recv.member`, or `member` when there is no receiver."""
        return f"{self.receiver}.{self.member}" if self.receiver else self.member
