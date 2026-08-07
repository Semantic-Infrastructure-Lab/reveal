"""B006: Silent broad exception handler detector.

Detects broad exception handlers (except Exception:) that produce no visible
signal on failure — no re-raise, no WARNING/ERROR/CRITICAL-level log, no
print — and no explanatory comment. This covers bare `pass` as well as
`logger.debug(...)` followed by a return/assignment: debug-level logging is
invisible in a normal run, so a handler that only logs at that level is just
as silent as one that does nothing at all (see BACK-983 / BACK-979/981/982:
this exact shape — `except Exception: logger.debug(...); return <empty>` —
was found to hide real infrastructure failures behind results that look like
a clean, valid empty output).

Also recognizes two visible-signal shapes beyond a direct logger/print call
(BACK-992): a call to a known helper that logs internally on the caller's
behalf (e.g. ``record_composed_error()``), and an assignment that records the
failure in-band on a result object (``result['status'] = 'query_failed'``,
``self.parse_error = ...``).
"""

import ast
import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin


class B006(BaseRule, ASTParsingMixin):
    """Detect silent broad exception handlers that swallow errors."""

    code = "B006"
    message = "Broad exception handler with no visible failure signal can hide bugs"
    category = RulePrefix.B
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    version = "1.2.0"

    # Logger/print calls that count as a *visible* signal. logger.debug() is
    # deliberately excluded — it's invisible in a normal run, so a handler
    # that only logs at debug level is still effectively silent.
    _VISIBLE_LOG_CALLS = frozenset({'warning', 'error', 'critical', 'exception'})

    # Helper methods known to emit a visible warning-level signal internally,
    # even though the call site here doesn't call logger directly (BACK-984's
    # ResourceAdapter.compose()/record_composed_error() pattern). Named
    # explicitly rather than matched by a broad "*_error()" heuristic — that
    # would risk exempting a genuinely silent handler that happens to call a
    # no-op method with an error-sounding name (BACK-992).
    _VISIBLE_HELPER_CALLS = frozenset({'record_composed_error'})

    # Dict-key / attribute names that, when assigned to inside an except
    # body, record the failure in-band for the caller to inspect instead of
    # (or alongside) a log call — e.g. result['status'] = 'query_failed',
    # self.parse_error = f"...". A real visible-signal pattern B006 used to
    # miss entirely (BACK-992). Kept to exact, unambiguous names so this
    # doesn't become a blanket escape hatch for actually-silent handlers.
    _ERROR_FIELD_NAMES = frozenset({'error', 'status', 'parse_error', 'failed'})

    # Pattern to detect explanatory comments near pass statement
    COMMENT_PATTERN = re.compile(r'#\s*\w+')

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for broad exception handlers with silent pass.

        Args:
            file_path: Path to Python file
            structure: Parsed structure (not used, we parse AST ourselves)
            content: File content

        Returns:
            List of detections
        """
        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        # Split content into lines for comment checking
        lines = content.split('\n')

        # Build parent map so handlers can walk up to the enclosing function
        parent_map: Dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[child] = parent

        # Walk the AST looking for problematic exception handlers
        for node in self._ast_walk(tree):
            if isinstance(node, ast.ExceptHandler):
                detection = self._check_handler(node, file_path, content, lines, parent_map)
                if detection:
                    detections.append(detection)

        return detections

    def _check_handler(
        self,
        node: ast.ExceptHandler,
        file_path: str,
        content: str,
        lines: List[str],
        parent_map: Optional[Dict[ast.AST, ast.AST]] = None,
    ) -> Optional[Detection]:
        """Check a single exception handler for silent broad exception swallowing."""
        if not self._is_broad_exception(node):
            return None
        if not self._is_silent(node):
            return None
        if self._has_explanatory_comment(node, lines):
            return None
        if parent_map and self._is_intentional_fallback(node, parent_map):
            return None

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
                "Consider:\n"
                "  1. Use specific exception types (ValueError, KeyError, etc.)\n"
                "  2. Add visible logging: logger.warning(f'Ignoring error: {e}') —\n"
                "     logger.debug() alone is invisible by default and does not count\n"
                "  3. Add comment explaining why silence is intentional\n"
                "  4. Re-raise if you can't handle: raise"
            ),
            context=context
        )

    def _is_broad_exception(self, node: ast.ExceptHandler) -> bool:
        """Check if exception handler catches Exception (broad catch).

        Args:
            node: AST ExceptHandler node

        Returns:
            True if catches Exception, BaseException, or tuple containing them
        """
        if node.type is None:
            # Bare except - handled by B001
            return False

        # Single exception: except Exception:
        if isinstance(node.type, ast.Name):
            return node.type.id in ('Exception', 'BaseException')

        # Tuple of exceptions: except (ValueError, Exception):
        if isinstance(node.type, ast.Tuple):
            for elt in node.type.elts:
                if isinstance(elt, ast.Name) and elt.id in ('Exception', 'BaseException'):
                    return True

        return False

    def _is_silent(self, node: ast.ExceptHandler) -> bool:
        """Check if exception handler body produces no visible failure signal.

        A handler is silent if it never re-raises and never calls a
        WARNING-or-higher log method or print — regardless of whether the
        body is a bare `pass`, a `return`/`continue`/`break`, an assignment,
        or `logger.debug(...)` followed by any of those. Debug-level logging
        does not count as visible: it's off by default in a normal run, so a
        handler that only logs at that level is just as silent to an actual
        user as one that does nothing (see BACK-983).

        Args:
            node: AST ExceptHandler node

        Returns:
            True if the handler body has no visible signal on failure
        """
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Raise):
                    return False
                if isinstance(sub, ast.Call):
                    func = sub.func
                    if isinstance(func, ast.Attribute):
                        name = func.attr
                    elif isinstance(func, ast.Name):
                        name = func.id
                    else:
                        name = None
                    if name in self._VISIBLE_LOG_CALLS or name == 'print':
                        return False
                    if name in self._VISIBLE_HELPER_CALLS:
                        return False
                if isinstance(sub, (ast.Assign, ast.AugAssign)):
                    targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                    if any(self._is_error_field_target(t) for t in targets):
                        return False
        return True

    def _is_error_field_target(self, target: ast.expr) -> bool:
        """True if an assignment target records failure state in-band.

        Recognizes ``self.parse_error = ...`` (attribute) and
        ``result['status'] = ...`` (subscript with a string-literal key)
        against a fixed, unambiguous name set (see ``_ERROR_FIELD_NAMES``).
        """
        if isinstance(target, ast.Attribute):
            return target.attr in self._ERROR_FIELD_NAMES
        if isinstance(target, ast.Subscript):
            key = target.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return key.value in self._ERROR_FIELD_NAMES
        return False

    # Keywords that indicate a docstring explicitly documents error-tolerance
    _DOCSTRING_ERROR_TOLERANCE = re.compile(
        r'\b(unavailable|raises any|if raises|on error|if error|if fails|'
        r'if not available|error is ignored|returns.*if.*error|error is expected)\b',
        re.IGNORECASE,
    )

    def _is_intentional_fallback(
        self, node: ast.ExceptHandler, parent_map: Dict[ast.AST, ast.AST]
    ) -> bool:
        """Return True when the handler is clearly intentional.

        Two patterns are recognized:
        1. Docstring explicitly documents error tolerance (e.g. "returns None if unavailable").
        2. Try-then-continue: the try block is NOT the last statement in the enclosing
           function/scope, meaning the except pass is used to fall through to alternative
           logic (e.g. subprocess call → fallback strategy).
        """
        # Walk up: ExceptHandler → Try → enclosing function
        try_node = parent_map.get(node)
        if not isinstance(try_node, ast.Try):
            return False
        func_node = parent_map.get(try_node)
        # Accept Try nested one level inside an if-guard at function scope
        if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            outer = parent_map.get(func_node) if func_node else None
            if not isinstance(outer, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return False
            func_node = outer

        body = func_node.body
        if not body:
            return False

        # Pattern 1: try-then-try — another try block follows, indicating a multi-attempt
        # fallback strategy (e.g. try approach A, if it fails try approach B).
        # This is intentional: the first except pass means "continue to next attempt".
        if try_node in body:
            idx = body.index(try_node)
            remaining = body[idx + 1:]
            if any(isinstance(s, ast.Try) for s in remaining):
                return True

        # Pattern 2: docstring explicitly documents error tolerance
        first = body[0]
        if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            return False

        docstring = first.value.value
        return bool(self._DOCSTRING_ERROR_TOLERANCE.search(docstring))

    def _has_explanatory_comment(self, node: ast.ExceptHandler, lines: List[str]) -> bool:
        """Check if exception handler has an explanatory comment.

        Looks for comments on:
        - The except line itself (inline comment)
        - Any line in the handler body (between except and last statement)

        Args:
            node: AST ExceptHandler node
            lines: Source code lines

        Returns:
            True if meaningful comment found
        """
        if not lines or node.lineno < 1:
            return False

        # Check except line (node.lineno is 1-indexed)
        except_line_idx = node.lineno - 1
        if except_line_idx < len(lines):
            if self.COMMENT_PATTERN.search(lines[except_line_idx]):
                return True

        # Check all lines in the handler body
        if node.body and hasattr(node.body[-1], 'lineno'):
            # Check from line after except to the last statement (inclusive)
            start_line_idx = except_line_idx + 1
            end_line_idx = node.body[-1].lineno  # This is 1-indexed, but we'll use it correctly

            for line_idx in range(start_line_idx, min(end_line_idx, len(lines))):
                if self.COMMENT_PATTERN.search(lines[line_idx]):
                    return True

        return False
