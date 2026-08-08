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

A third shape (BACK-989): the exception is captured into a plain variable
inside the handler (``error = str(e)``), and that variable is read again by
a *later* statement in the same enclosing block (``results.append({'error':
error, ...})``) — visible to the caller, just one statement outside the
handler body itself.

BACK-1011: this rule was Python-only (`file_patterns = ['.py']`) even though
the same bug shape — a broad ``catch`` with no visible failure signal — is
just as real in any exception-based language. C# support was added as the
first cross-language port (tree-sitter's `catch_clause` node, checked for a
`throw`/re-raise or a visible logging call in the body). It's deliberately
a simpler heuristic than the Python side: no docstring-tolerance or
deferred-signal detection yet, just bare/`Exception`-typed catch + empty-of-
signal body. Extending to Java/JS/TS/PHP/C++ (which share the same
`catch_clause` node kind) or Kotlin/Swift (`catch_block`) is mechanical
from here — see BACK-1011 for the remaining language list.
"""

import ast
import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin, TreeSitterParsingMixin
from ...core import node_children


class B006(BaseRule, ASTParsingMixin, TreeSitterParsingMixin):
    """Detect silent broad exception handlers that swallow errors."""

    code = "B006"
    message = "Broad exception handler with no visible failure signal can hide bugs"
    category = RulePrefix.B
    severity = Severity.MEDIUM
    file_patterns = ['.py', '.cs']
    version = "1.5.0"

    _CS_LANGUAGE = 'csharp'
    _CS_BROAD_TYPES = frozenset({'Exception', 'System.Exception'})
    # C#'s ILogger convention: Trace/Debug are invisible by default (same
    # rationale as Python's logger.debug exclusion above), so only
    # Warning/Error/Critical count as a visible signal.
    _CS_VISIBLE_LOG_METHODS = frozenset({
        'LogWarning', 'LogError', 'LogCritical',
        'WriteLine', 'Write',  # Console.Error.Write(Line) / Console.Write(Line)
    })

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
    _VISIBLE_HELPER_CALLS = frozenset({
        'record_composed_error', 'create_error', 'create_error_result',
    })

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
        if file_path.endswith('.cs'):
            return self._check_csharp(file_path, content)

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
        if parent_map and self._has_deferred_visible_signal(node, parent_map):
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
                if isinstance(sub, ast.Dict) and self._has_error_field_key(sub):
                    return False
        return True

    def _has_error_field_key(self, node: ast.Dict) -> bool:
        """True if a dict literal has a string-literal key recording failure state in-band.

        Covers ``return {'error': str(e), ...}`` / ``return {**base, 'error':
        ..., 'status': 'failure', ...}`` — the same in-band-signal idea as
        ``_is_error_field_target`` (BACK-992), extended to dict *literals*
        (construction), not just assignment to an existing dict/attribute.
        This is the dominant real shape adapter handlers use to surface a
        failure to the caller (BACK-989 triage).
        """
        return any(
            isinstance(key, ast.Constant) and isinstance(key.value, str)
            and key.value in self._ERROR_FIELD_NAMES
            for key in node.keys
        )

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

    # Keywords that indicate a docstring explicitly documents error-tolerance.
    # Deliberately covers common paraphrases ("fails for any reason", "best
    # effort", "degrades gracefully") in addition to the original exact
    # phrases — BACK-989 triage found several genuinely-documented fallbacks
    # this missed purely on wording (e.g. "falls back ... if X fails for any
    # reason" didn't match the narrower "if fails").
    _DOCSTRING_ERROR_TOLERANCE = re.compile(
        r'\b(unavailable|raises any|if raises|on error|if error|if fails|fails\b|'
        r'if not available|error is ignored|returns.*if.*error|error is expected|'
        r'any (error|failure)|on (any )?failure|best.effort|degrades? gracefully)\b',
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

    def _has_deferred_visible_signal(
        self, node: ast.ExceptHandler, parent_map: Dict[ast.AST, ast.AST]
    ) -> bool:
        """Return True if the handler captures the exception into a variable
        that a later statement in the same block actually reads — e.g.::

            except Exception as e:
                reachable = False
                error = str(e)
            results.append({'reachable': reachable, 'error': error})

        The failure IS visible to the caller, just one statement outside the
        handler body itself, which ``_is_silent``'s body-only walk can't see
        (BACK-989 triage found this exact shape repeatedly: a variable set in
        the handler from ``str(e)``/an f-string over the exception, read back
        a line or two later in a returned/logged/appended value).

        Requires the captured variable's *value* to actually reference the
        exception binding — a plain ``ok = False`` assigned alongside it
        does not by itself qualify — so a genuinely silent handler with an
        unrelated variable set in the body doesn't accidentally pass.
        """
        if node.name is None:
            return False  # no `as e` binding to trace

        captured: set = set()
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
                value = stmt.value
            elif isinstance(stmt, ast.AugAssign):
                targets = [stmt.target]
                value = stmt.value
            else:
                continue
            references_exc = any(
                isinstance(sub, ast.Name) and sub.id == node.name
                for sub in ast.walk(value)
            )
            if not references_exc:
                continue
            for t in targets:
                if isinstance(t, ast.Tuple):
                    captured.update(elt.id for elt in t.elts if isinstance(elt, ast.Name))
                elif isinstance(t, ast.Name):
                    captured.add(t.id)
        if not captured:
            return False

        try_node = parent_map.get(node)
        if not isinstance(try_node, ast.Try):
            return False
        body = self._get_enclosing_body(try_node, parent_map)
        if not body or try_node not in body:
            return False

        for later in body[body.index(try_node) + 1:]:
            for sub in ast.walk(later):
                if (isinstance(sub, ast.Name) and sub.id in captured
                        and isinstance(sub.ctx, ast.Load)):
                    return True
        return False

    def _get_enclosing_body(
        self, node: ast.AST, parent_map: Dict[ast.AST, ast.AST]
    ) -> Optional[List[ast.stmt]]:
        """Return the statement list of *node*'s immediate parent that contains it."""
        parent = parent_map.get(node)
        if parent is None:
            return None
        for attr in ('body', 'orelse', 'finalbody'):
            candidate = getattr(parent, attr, None)
            if isinstance(candidate, list) and node in candidate:
                return candidate
        return None

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

    # ── C# (BACK-1011) ──────────────────────────────────────────────────────

    def _check_csharp(self, file_path: str, content: str) -> List[Detection]:
        """Check C# source for silent broad `catch` clauses.

        Args:
            file_path: Path to C# file
            content: File content

        Returns:
            List of detections
        """
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._CS_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')
        for node in self._ts_walk(root):
            if node.kind() != 'catch_clause':
                continue
            if not self._cs_is_broad_catch(node, content_bytes):
                continue
            if self._cs_has_visible_signal(node, content_bytes):
                continue
            if self._cs_has_explanatory_comment(node):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=node.start_position().row + 1,
                column=node.start_position().column + 1,
                suggestion=(
                    "Consider:\n"
                    "  1. Catch specific exception types instead of Exception\n"
                    "  2. Add visible logging: _logger.LogWarning(ex, \"...\") —\n"
                    "     LogTrace/LogDebug alone are invisible by default and do not count\n"
                    "  3. Re-throw if you can't handle it: throw;"
                ),
                context=self._ts_node_text(node, content_bytes).split('\n')[0],
            ))

        return detections

    def _cs_is_broad_catch(self, node, content_bytes: bytes) -> bool:
        """True for a bare `catch { }` or a `catch (Exception e) { }`.

        A bare catch (no `catch_declaration` child at all) catches literally
        everything, same as Python's bare `except:` (B001's territory in
        Python, folded into this rule for C# since there's no separate B001
        port yet — see BACK-1011).
        """
        declaration = next(
            (c for c in node_children(node) if c.kind() == 'catch_declaration'), None
        )
        if declaration is None:
            return True

        type_node = next(
            (c for c in node_children(declaration)
             if c.kind() in ('identifier', 'qualified_name')),
            None
        )
        if type_node is None:
            return True
        return self._ts_node_text(type_node, content_bytes) in self._CS_BROAD_TYPES

    def _cs_has_visible_signal(self, node, content_bytes: bytes) -> bool:
        """True if the catch body re-throws or calls a visible logging method."""
        block = next((c for c in node_children(node) if c.kind() == 'block'), None)
        if block is None:
            return False

        for descendant in self._ts_walk(block):
            if descendant.kind() == 'throw_statement':
                return True
            if descendant.kind() == 'invocation_expression':
                function = node_children(descendant)[0] if node_children(descendant) else None
                if function is None:
                    continue
                name = self._ts_node_text(function, content_bytes).rsplit('.', 1)[-1]
                if name in self._CS_VISIBLE_LOG_METHODS:
                    return True
        return False

    def _cs_has_explanatory_comment(self, node) -> bool:
        """True if a `// ...` or `/* ... */` comment appears anywhere inside
        the catch clause — mirrors the Python side's comment exemption
        (BACK-1011: real corpus check found ~1/3 of raw hits were an
        explicitly-commented intentional swallow, e.g.
        `catch { // Logged at lower levels }`)."""
        return any(descendant.kind() == 'comment' for descendant in self._ts_walk(node))
