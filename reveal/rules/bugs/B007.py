"""B007: Adapter exception handler logs a failure but never records it in the
Output Contract trust envelope.

BACK-1017 — the structural gap behind BACK-1016. B006 already treats a call
to record_composed_error()/create_error()/create_error_result() as
interchangeable with a visible log call (both count as "not silent"). That
equivalence is correct for general code, but wrong inside a ResourceAdapter:
a bare logger.warning() only reaches stderr (reveal configures no logging
handlers — no basicConfig/addHandler anywhere in reveal/, so it's Python's
lastResort stderr emitter), invisible to --format json and any piped/tee'd
DD run. record_composed_error() is the only channel that lands in
meta.errors and lowers meta.confidence — the machine-readable envelope the
Output Contract exists for. A handler that logs but never calls the
envelope helper is B006-clean yet still hides the failure from every
consumer that trusts the JSON envelope over stderr.

This is why BACK-1016's three sites (overview.py/architecture.py's
_run_scope/_run_git_log) survived the BACK-981/982/984 remediation sweep:
they had a logger.warning() call, so B006's silence check passed.

Scope (option (a) from BACK-1017, chosen over redefining B006's meaning):
narrow and adapter-specific — only fires on exception handlers inside
functions that operate on a ResourceAdapter (or subclass, by name — reveal
has no cross-file type resolution, so this matches the annotation/base-class
name literally, e.g. 'OverviewAdapter', 'ResourceAdapter'). This covers both
observed shapes: a method on an Adapter-derived class (self), and a
module-level helper function that takes the adapter as a parameter (the
dominant pattern in overview.py/architecture.py/deps.py/hotspots.py — see
BACK-1017's note that a naive "enclosing class is a ResourceAdapter" check
alone would miss these).

BACK-2254 (option C): ``note_warning()`` counts as an envelope call (it writes the result's
meta.warnings, the disclosure for a failure that leaves the rest of the answer standing), and so
does a handler that adds its exception to a local list the function returns: the failure leaves as
data, and the caller that builds the result records it (help.py's ``_adapters_with_schema``).
A computed default (``return {}``) is still flagged.

internal=True: 'Adapter'-suffixed classes and record_composed_error() are
reveal's own conventions, not something external codebases follow — this
rule only ever fires on reveal's own source (dogfooded via reveal://source
or a direct check of reveal/adapters/**/*.py).
"""

import ast
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity, RuleScope
from ..base_mixins import ASTParsingMixin
from ...utils.pyparse import statement_index


class B007(BaseRule, ASTParsingMixin):
    """Detect adapter exception handlers that log but don't record_composed_error()."""

    code = "B007"
    scope = RuleScope.FILE
    message = "Adapter exception handler logs the failure but never records it in the Output Contract envelope"
    category = RulePrefix.B
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    internal = True  # reveal's own ResourceAdapter/record_composed_error convention
    version = "1.1.0"

    # Same set B006 treats as a visible signal (logger.debug excluded — off by
    # default in a normal run, so not a real signal either way).
    _VISIBLE_LOG_CALLS = frozenset({'warning', 'error', 'critical', 'exception'})

    # The Output Contract trust-envelope channel(s) — same names B006 already
    # (over-)trusts as interchangeable with a log call. B007 exists precisely
    # because they are NOT interchangeable inside adapter code.
    # note_warning() is the shared meta.warnings writer (BACK-2254).
    _ENVELOPE_CALLS = frozenset({'record_composed_error', 'create_error', 'create_error_result',
                                 'note_warning'})

    # A handler that hands its exception to a returned collection with one of these.
    _COLLECT_CALLS = frozenset({'append', 'extend', 'add'})

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        if not file_path.endswith('.py'):
            return []

        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        statements, parent_map = statement_index(tree)

        # Handlers grouped by their nearest enclosing function — a nested function's
        # own handlers are checked against the nested function's own adapter-param
        # status separately, not inherited from the outer scope. Built on the first
        # adapter function, so a file without one never pays for it.
        handlers_by_function: Optional[Dict[int, List[ast.ExceptHandler]]] = None

        for node in statements:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if self._adapter_param_name(node, parent_map) is None:
                continue
            if handlers_by_function is None:
                handlers_by_function = {}
                for handler in statements:
                    if isinstance(handler, ast.ExceptHandler):
                        owner = self._nearest_enclosing_function(handler, parent_map)
                        handlers_by_function.setdefault(id(owner), []).append(handler)
            for sub in handlers_by_function.get(id(node), ()):
                detection = self._check_handler(sub, file_path, content, node)
                if detection:
                    detections.append(detection)

        return detections

    def _check_handler(self, node: ast.ExceptHandler, file_path: str, content: str,
                       function: ast.AST) -> Optional[Detection]:
        """Flag a handler that logs visibly but never calls the envelope helper."""
        has_visible_log = False
        has_envelope_call = False
        collected: List[str] = []
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if not isinstance(sub, ast.Call):
                    continue
                func = sub.func
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                else:
                    name = None
                if name in self._VISIBLE_LOG_CALLS:
                    has_visible_log = True
                if name in self._ENVELOPE_CALLS:
                    has_envelope_call = True
                target = self._collection_of_exception(sub, node.name)
                if target:
                    collected.append(target)

        if not (has_visible_log and not has_envelope_call):
            return None
        if collected and set(collected) & self._returned_names(function):
            return None  # the failure is returned to the caller as data (BACK-2254)

        context = None
        try:
            segment = ast.get_source_segment(content, node)
            if segment:
                context = '\n'.join(segment.split('\n')[:2])
        except Exception:  # noqa: BLE001 - ast.get_source_segment can raise unexpectedly
            context = None

        return self.create_detection(
            file_path=file_path,
            line=node.lineno,
            column=node.col_offset + 1,
            suggestion=(
                "This handler logs the failure but never calls record_composed_error() "
                "(or create_error()/create_error_result()/note_warning()) — the log is stderr-only "
                "(reveal sets up no logging handlers) and invisible to --format json "
                "consumers. Call the adapter's record_composed_error() so the failure "
                "lands in meta.errors/confidence, note_warning() when the rest of the answer "
                "stands, or return the failure to the caller that builds the result."
            ),
            context=context,
        )

    def _collection_of_exception(self, call: ast.Call, exc_name: Optional[str]) -> Optional[str]:
        """``X`` when ``call`` is ``X.append/extend/add(...)`` with the exception in its args."""
        func = call.func
        if not (exc_name and isinstance(func, ast.Attribute) and func.attr in self._COLLECT_CALLS
                and isinstance(func.value, ast.Name)):
            return None
        for arg in call.args:
            if any(isinstance(n, ast.Name) and n.id == exc_name for n in ast.walk(arg)):
                return func.value.id
        return None

    def _returned_names(self, function: ast.AST) -> set:
        """Names read in the function's own ``return`` values (nested functions excluded)."""
        names: set = set()
        stack = list(ast.iter_child_nodes(function))
        while stack:
            child = stack.pop()
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(child, ast.Return) and child.value is not None:
                names.update(n.id for n in ast.walk(child.value) if isinstance(n, ast.Name))
            stack.extend(ast.iter_child_nodes(child))
        return names

    def _adapter_param_name(self, node, parent_map: Dict[ast.AST, ast.AST]) -> Optional[str]:
        """Return the name of the parameter that refers to a ResourceAdapter
        (or subclass), or None if this function has none."""
        args = node.args
        all_args = list(getattr(args, 'posonlyargs', [])) + list(args.args) + list(args.kwonlyargs)

        for arg in all_args:
            name = self._annotation_name(arg.annotation)
            if name and name.endswith('Adapter'):
                return arg.arg

        # No annotated adapter param — is this a method on an Adapter-derived class?
        if all_args and all_args[0].arg in ('self', 'cls'):
            enclosing_class = self._enclosing_class(node, parent_map)
            if enclosing_class and self._class_is_adapter(enclosing_class):
                return all_args[0].arg

        return None

    def _annotation_name(self, annotation: Optional[ast.expr]) -> Optional[str]:
        """Extract a bare name from a type annotation, unwrapping Optional[X]/
        forward-ref strings/attribute access — 'good enough' matching, not
        full type resolution (reveal has no cross-file resolver)."""
        if annotation is None:
            return None
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(annotation, ast.Attribute):
            return annotation.attr
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            return annotation.value
        if isinstance(annotation, ast.Subscript):
            slice_node = annotation.slice
            if isinstance(slice_node, ast.Index):  # py3.8 compat
                slice_node = slice_node.value
            return self._annotation_name(slice_node)
        return None

    def _enclosing_class(self, node: ast.AST, parent_map: Dict[ast.AST, ast.AST]) -> Optional[ast.ClassDef]:
        current = parent_map.get(node)
        while current is not None:
            if isinstance(current, ast.ClassDef):
                return current
            current = parent_map.get(current)
        return None

    def _class_is_adapter(self, class_node: ast.ClassDef) -> bool:
        for base in class_node.bases:
            if isinstance(base, ast.Name) and base.id.endswith('Adapter'):
                return True
            if isinstance(base, ast.Attribute) and base.attr.endswith('Adapter'):
                return True
        return False

    def _nearest_enclosing_function(self, node: ast.AST, parent_map: Dict[ast.AST, ast.AST]):
        current = parent_map.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current
            current = parent_map.get(current)
        return None
