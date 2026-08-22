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
just as real in any exception-based language. Cross-language ports (tree-
sitter's `catch_clause` node, checked for a `throw`/re-raise or a visible
logging call in the body) now cover C#, Java, JavaScript, TypeScript, and
PHP. Kotlin and Swift share the same heuristic but a different node kind
(`catch_block`, not `catch_clause`). All are deliberately simpler heuristics
than the Python side: no docstring-tolerance or deferred-signal detection,
just broad-catch + empty-of-signal body (+ explanatory-comment exemption).
"Broad" itself is language-specific: C#/Java/PHP/Kotlin require a bare or
Exception/Throwable-typed catch; JavaScript/TypeScript have no catch-type
syntax at all, so every catch is broad there and only the silence check
discriminates; Swift narrows only when a pattern explicitly types the catch
via `as`/an enum-case match to something other than `Error`/`NSError` — a
bare `catch {}` or an untyped `catch let e` stays broad. C++ (`...`
ellipsis catch-all) remains open — see BACK-1011.
"""

import ast
import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin, TreeSitterParsingMixin
from ...core import node_children, _zero_arg


class B006(BaseRule, ASTParsingMixin, TreeSitterParsingMixin):
    """Detect silent broad exception handlers that swallow errors."""

    code = "B006"
    message = "Broad exception handler with no visible failure signal can hide bugs"
    category = RulePrefix.B
    severity = Severity.MEDIUM
    file_patterns = [
        '.py', '.cs', '.java',
        '.js', '.jsx', '.mjs', '.cjs', '.ts',
        '.php', '.kt', '.kts', '.swift',
        '.cpp', '.cc', '.cxx', '.hpp', '.hh', '.h++',
    ]
    version = "1.8.0"

    _CS_LANGUAGE = 'csharp'
    _CS_BROAD_TYPES = frozenset({'Exception', 'System.Exception'})
    # C#'s ILogger convention: Trace/Debug are invisible by default (same
    # rationale as Python's logger.debug exclusion above), so only
    # Warning/Error/Critical count as a visible signal.
    _CS_VISIBLE_LOG_METHODS = frozenset({
        'LogWarning', 'LogError', 'LogCritical',
        'WriteLine', 'Write',  # Console.Error.Write(Line) / Console.Write(Line)
    })

    _JAVA_LANGUAGE = 'java'
    _JAVA_BROAD_TYPES = frozenset({'Exception', 'RuntimeException', 'Throwable'})
    # SLF4J/JUL naming differs (warn vs warning, error vs severe) — cover both
    # conventions. printStackTrace is the single most common raw Java
    # swallow-with-signal idiom, included even though it targets stderr
    # rather than a logger.
    _JAVA_VISIBLE_METHODS = frozenset({
        'error', 'warn', 'warning', 'severe', 'fatal', 'critical', 'printStackTrace',
    })

    _JS_LANGUAGE = 'javascript'
    _TS_LANGUAGE = 'typescript'
    # console.* is always emitted (no configurable level like a backend
    # logger), so ANY console method counts as visible — unlike the
    # Debug/Trace exclusion elsewhere in this rule. error/warn(ing) on any
    # other object (a custom logger) uses the same name-only heuristic as
    # the other languages.
    _JS_VISIBLE_METHODS = frozenset({'error', 'warn', 'warning'})

    _PHP_LANGUAGE = 'php'
    _PHP_BROAD_TYPES = frozenset({'Exception', 'Throwable'})
    _PHP_VISIBLE_FUNCTIONS = frozenset({'error_log', 'trigger_error'})
    # PSR-3 log levels, excluding debug/info/notice (invisible-by-default
    # equivalents, same rationale as the Python/C#/Java debug exclusions).
    _PHP_VISIBLE_METHODS = frozenset({
        'error', 'warning', 'critical', 'alert', 'emergency',
    })

    _KOTLIN_LANGUAGE = 'kotlin'
    _KOTLIN_BROAD_TYPES = frozenset({'Exception', 'Throwable', 'RuntimeException'})
    # Real corpus (Tivi) uses Kermit ('logger.e { }'/'Logger.e(t) { }') and
    # Android Log/Timber ('Log.e'/'Timber.e') conventions almost
    # exclusively — single-letter e/w method names are the idiom, not an
    # abbreviation of something else. 'd' (debug) and 'i' (info) excluded,
    # same invisible-by-default rationale as every other language here.
    _KOTLIN_VISIBLE_METHODS = frozenset({
        'e', 'w', 'error', 'warn', 'warning', 'severe', 'fatal', 'critical', 'printStackTrace',
    })

    _SWIFT_LANGUAGE = 'swift'
    # Swift's Error protocol has no Java-style Exception/Throwable split —
    # NSError is the other broad catch-all in Cocoa-interop code.
    _SWIFT_BROAD_TYPES = frozenset({'Error', 'NSError'})
    # Swift has no built-in level-gated logger convention as dominant as
    # Java/C#'s — real corpus (Kickstarter iOS) overwhelmingly uses bare
    # print()/NSLog() in catch bodies, not a logging framework.
    _SWIFT_VISIBLE_FUNCTIONS = frozenset({'print', 'NSLog'})
    _SWIFT_VISIBLE_METHODS = frozenset({
        'error', 'warning', 'warn', 'critical', 'fatal', 'record',
    })

    _CPP_LANGUAGE = 'cpp'
    # No RuntimeException-style split in C++ — std::exception is the root
    # of the standard hierarchy (the analog of Java's Throwable), so it's
    # the only named broad type; `catch (...)` (ellipsis) is broad on its
    # own and handled separately since it has no type node at all.
    _CPP_BROAD_TYPES = frozenset({'exception'})
    # Real corpus (Godot) has almost no try/catch in its own code — it uses
    # error-return macros instead — so this is a generic heuristic rather
    # than one calibrated against a dominant idiom: std::cerr/std::clog
    # stream output, the C stderr functions, and the same
    # error/warn(ing)-named-method convention (spdlog::error, logger->error)
    # used by every other language port here.
    _CPP_VISIBLE_STREAMS = frozenset({'cerr', 'clog', 'std::cerr', 'std::clog'})
    _CPP_VISIBLE_FUNCTIONS = frozenset({'fprintf', 'fputs', 'perror'})
    _CPP_VISIBLE_METHODS = frozenset({
        'error', 'warn', 'warning', 'critical', 'fatal', 'severe',
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
        if file_path.endswith('.java'):
            return self._check_java(file_path, content)
        if file_path.endswith(('.js', '.jsx', '.mjs', '.cjs')):
            return self._check_js_like(file_path, content, self._JS_LANGUAGE)
        if file_path.endswith('.ts'):
            return self._check_js_like(file_path, content, self._TS_LANGUAGE)
        if file_path.endswith('.php'):
            return self._check_php(file_path, content)
        if file_path.endswith(('.kt', '.kts')):
            return self._check_kotlin(file_path, content)
        if file_path.endswith('.swift'):
            return self._check_swift(file_path, content)
        if file_path.endswith(('.cpp', '.cc', '.cxx', '.hpp', '.hh', '.h++')):
            return self._check_cpp(file_path, content)

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
            if _zero_arg(node, 'kind') != 'catch_clause':
                continue
            if not self._cs_is_broad_catch(node, content_bytes):
                continue
            if self._cs_has_visible_signal(node, content_bytes):
                continue
            if self._cs_has_explanatory_comment(node):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=_zero_arg(node, 'start_position').row + 1,
                column=_zero_arg(node, 'start_position').column + 1,
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
            (c for c in node_children(node) if _zero_arg(c, 'kind') == 'catch_declaration'), None
        )
        if declaration is None:
            return True

        type_node = next(
            (c for c in node_children(declaration)
             if _zero_arg(c, 'kind') in ('identifier', 'qualified_name')),
            None
        )
        if type_node is None:
            return True
        return self._ts_node_text(type_node, content_bytes) in self._CS_BROAD_TYPES

    def _cs_has_visible_signal(self, node, content_bytes: bytes) -> bool:
        """True if the catch body re-throws or calls a visible logging method."""
        block = next((c for c in node_children(node) if _zero_arg(c, 'kind') == 'block'), None)
        if block is None:
            return False

        for descendant in self._ts_walk(block):
            if _zero_arg(descendant, 'kind') == 'throw_statement':
                return True
            if _zero_arg(descendant, 'kind') == 'invocation_expression':
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
        return any(_zero_arg(descendant, 'kind') == 'comment' for descendant in self._ts_walk(node))

    # ── Java (BACK-1011) ─────────────────────────────────────────────────────

    def _check_java(self, file_path: str, content: str) -> List[Detection]:
        """Check Java source for silent broad `catch` clauses."""
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._JAVA_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')
        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'catch_clause':
                continue
            if not self._java_is_broad_catch(node, content_bytes):
                continue
            if self._java_has_visible_signal(node, content_bytes):
                continue
            if any(_zero_arg(d, 'kind') == 'comment' for d in self._ts_walk(node)):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=_zero_arg(node, 'start_position').row + 1,
                column=_zero_arg(node, 'start_position').column + 1,
                suggestion=(
                    "Consider:\n"
                    "  1. Catch specific exception types instead of Exception/Throwable\n"
                    "  2. Add visible logging: log.error(\"...\", e) —\n"
                    "     debug/trace-level logging alone is invisible by default and does not count\n"
                    "  3. Re-throw if you can't handle it: throw e; / throw new ...(e);"
                ),
                context=self._ts_node_text(node, content_bytes).split('\n')[0],
            ))

        return detections

    def _java_is_broad_catch(self, node, content_bytes: bytes) -> bool:
        """True if any type in a (possibly multi-catch `A | B`) clause is broad.

        Java always requires a typed parameter — there's no bare `catch {}`.
        """
        param = next(
            (c for c in node_children(node) if _zero_arg(c, 'kind') == 'catch_formal_parameter'), None
        )
        if param is None:
            return False
        catch_type = next(
            (c for c in node_children(param) if _zero_arg(c, 'kind') == 'catch_type'), None
        )
        if catch_type is None:
            return False
        return any(
            self._ts_node_text(t, content_bytes) in self._JAVA_BROAD_TYPES
            for t in node_children(catch_type) if _zero_arg(t, 'kind') == 'type_identifier'
        )

    def _java_has_visible_signal(self, node, content_bytes: bytes) -> bool:
        """True if the catch body re-throws or calls a visible logging method."""
        block = next((c for c in node_children(node) if _zero_arg(c, 'kind') == 'block'), None)
        if block is None:
            return False

        for descendant in self._ts_walk(block):
            if _zero_arg(descendant, 'kind') == 'throw_statement':
                return True
            if _zero_arg(descendant, 'kind') == 'method_invocation':
                if self._java_call_name(descendant, content_bytes) in self._JAVA_VISIBLE_METHODS:
                    return True
        return False

    def _java_call_name(self, node, content_bytes: bytes) -> Optional[str]:
        """Extract a `method_invocation`'s callee name.

        Java's grammar is flat (`identifier '.' identifier argument_list`
        for a member call, not a nested member-access node like C#), so the
        name is the identifier immediately after a `.` token if present,
        else the sole identifier (a bare, non-member call).
        """
        children = node_children(node)
        for i, child in enumerate(children):
            if _zero_arg(child, 'kind') == '.' and i + 1 < len(children):
                return self._ts_node_text(children[i + 1], content_bytes)
        ident = next((c for c in children if _zero_arg(c, 'kind') == 'identifier'), None)
        return self._ts_node_text(ident, content_bytes) if ident else None

    # ── JavaScript / TypeScript (BACK-1011) ─────────────────────────────────

    def _check_js_like(self, file_path: str, content: str, language: str) -> List[Detection]:
        """Check JS/TS source for silent `catch` clauses.

        Neither language has catch-type syntax — every `catch` is
        unconditionally broad, so only the silence check discriminates
        (unlike the typed-language ports above).
        """
        root, detections = self._parse_treesitter_or_skip(content, file_path, language)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')
        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'catch_clause':
                continue
            if self._js_has_visible_signal(node, content_bytes):
                continue
            if any(_zero_arg(d, 'kind') == 'comment' for d in self._ts_walk(node)):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=_zero_arg(node, 'start_position').row + 1,
                column=_zero_arg(node, 'start_position').column + 1,
                suggestion=(
                    "Consider:\n"
                    "  1. Add visible logging: console.error(err) — any console.* call counts\n"
                    "  2. Re-throw if you can't handle it: throw err;\n"
                    "  3. Add a comment explaining why silence is intentional"
                ),
                context=self._ts_node_text(node, content_bytes).split('\n')[0],
            ))

        return detections

    def _js_has_visible_signal(self, node, content_bytes: bytes) -> bool:
        """True if the catch body re-throws or calls a visible logging method."""
        block = next((c for c in node_children(node) if _zero_arg(c, 'kind') == 'statement_block'), None)
        if block is None:
            return False

        for descendant in self._ts_walk(block):
            if _zero_arg(descendant, 'kind') == 'throw_statement':
                return True
            if _zero_arg(descendant, 'kind') != 'call_expression':
                continue
            callee = node_children(descendant)[0] if node_children(descendant) else None
            if callee is None:
                continue
            if _zero_arg(callee, 'kind') == 'identifier':
                if self._ts_node_text(callee, content_bytes) in self._JS_VISIBLE_METHODS:
                    return True
            elif _zero_arg(callee, 'kind') == 'member_expression':
                members = node_children(callee)
                if not members:
                    continue
                obj_text = self._ts_node_text(members[0], content_bytes)
                prop = next((c for c in members if _zero_arg(c, 'kind') == 'property_identifier'), None)
                prop_text = self._ts_node_text(prop, content_bytes) if prop else None
                if obj_text == 'console':
                    return True
                if prop_text in self._JS_VISIBLE_METHODS:
                    return True
        return False

    # ── PHP (BACK-1011) ──────────────────────────────────────────────────────

    def _check_php(self, file_path: str, content: str) -> List[Detection]:
        """Check PHP source for silent broad `catch` clauses."""
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._PHP_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')
        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'catch_clause':
                continue
            if not self._php_is_broad_catch(node, content_bytes):
                continue
            if self._php_has_visible_signal(node, content_bytes):
                continue
            if any(_zero_arg(d, 'kind') == 'comment' for d in self._ts_walk(node)):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=_zero_arg(node, 'start_position').row + 1,
                column=_zero_arg(node, 'start_position').column + 1,
                suggestion=(
                    "Consider:\n"
                    "  1. Catch specific exception types instead of Exception/Throwable\n"
                    "  2. Add visible logging: error_log(...) or $logger->error(...) —\n"
                    "     debug/info-level logging alone is invisible by default and does not count\n"
                    "  3. Re-throw if you can't handle it: throw $e;"
                ),
                context=self._ts_node_text(node, content_bytes).split('\n')[0],
            ))

        return detections

    def _php_is_broad_catch(self, node, content_bytes: bytes) -> bool:
        """True if any type in a (possibly multi-catch `A | B`) clause is broad."""
        type_list = next((c for c in node_children(node) if _zero_arg(c, 'kind') == 'type_list'), None)
        if type_list is None:
            return False
        for named_type in node_children(type_list):
            if _zero_arg(named_type, 'kind') != 'named_type':
                continue
            name_node = next(
                (n for n in self._ts_walk(named_type) if _zero_arg(n, 'kind') == 'name'), None
            )
            if name_node and self._ts_node_text(name_node, content_bytes) in self._PHP_BROAD_TYPES:
                return True
        return False

    def _php_has_visible_signal(self, node, content_bytes: bytes) -> bool:
        """True if the catch body re-throws or calls a visible logging function/method."""
        block = next(
            (c for c in node_children(node) if _zero_arg(c, 'kind') == 'compound_statement'), None
        )
        if block is None:
            return False

        for descendant in self._ts_walk(block):
            if _zero_arg(descendant, 'kind') == 'throw_expression':
                return True
            if _zero_arg(descendant, 'kind') == 'function_call_expression':
                name_node = next(
                    (c for c in node_children(descendant) if _zero_arg(c, 'kind') == 'name'), None
                )
                if name_node and self._ts_node_text(name_node, content_bytes) in self._PHP_VISIBLE_FUNCTIONS:
                    return True
            if _zero_arg(descendant, 'kind') == 'member_call_expression':
                # The method name is the LAST direct 'name' child (the first
                # 'name' inside member_access_expression belongs to the
                # receiver, e.g. `$this->logger` in `$this->logger->error()`).
                names = [c for c in node_children(descendant) if _zero_arg(c, 'kind') == 'name']
                if names and self._ts_node_text(names[-1], content_bytes) in self._PHP_VISIBLE_METHODS:
                    return True
        return False

    # ── Kotlin (BACK-1011) ───────────────────────────────────────────────────

    def _check_kotlin(self, file_path: str, content: str) -> List[Detection]:
        """Check Kotlin source for silent broad `catch` clauses.

        Kotlin's `catch_block` is a different tree-sitter node kind from the
        `catch_clause` shared by C#/Java/JS/TS/PHP, but Kotlin always
        requires a typed parameter (no bare `catch {}`, unlike Java/C#), so
        the broad-type check mirrors Java's rather than needing a
        no-declaration fallback.
        """
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._KOTLIN_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')
        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'catch_block':
                continue
            if not self._kotlin_is_broad_catch(node, content_bytes):
                continue
            if self._kotlin_has_visible_signal(node, content_bytes):
                continue
            if any('comment' in _zero_arg(d, 'kind') for d in self._ts_walk(node)):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=_zero_arg(node, 'start_position').row + 1,
                column=_zero_arg(node, 'start_position').column + 1,
                suggestion=(
                    "Consider:\n"
                    "  1. Catch specific exception types instead of Exception/Throwable\n"
                    "  2. Add visible logging: logger.e(e) { \"...\" } / Log.w(TAG, ...) —\n"
                    "     debug/verbose-level logging alone is invisible by default and does not count\n"
                    "  3. Re-throw if you can't handle it: throw e"
                ),
                context=self._ts_node_text(node, content_bytes).split('\n')[0],
            ))

        return detections

    def _kotlin_is_broad_catch(self, node, content_bytes: bytes) -> bool:
        """True if the catch parameter's type is Exception/Throwable/RuntimeException."""
        type_node = next(
            (c for c in node_children(node) if _zero_arg(c, 'kind') == 'user_type'), None
        )
        if type_node is None:
            return False
        return self._ts_node_text(type_node, content_bytes) in self._KOTLIN_BROAD_TYPES

    def _kotlin_has_visible_signal(self, node, content_bytes: bytes) -> bool:
        """True if the catch body re-throws or calls a visible logging method."""
        statements = next((c for c in node_children(node) if _zero_arg(c, 'kind') == 'statements'), None)
        if statements is None:
            return False

        for descendant in self._ts_walk(statements):
            if _zero_arg(descendant, 'kind') == 'jump_expression':
                first = node_children(descendant)
                if first and _zero_arg(first[0], 'kind') == 'throw':
                    return True
            if _zero_arg(descendant, 'kind') != 'call_expression':
                continue
            callee = node_children(descendant)[0] if node_children(descendant) else None
            if callee is None:
                continue
            if _zero_arg(callee, 'kind') == 'navigation_expression':
                suffix = next(
                    (c for c in node_children(callee) if _zero_arg(c, 'kind') == 'navigation_suffix'), None
                )
                if suffix is None:
                    continue
                name_node = next(
                    (c for c in node_children(suffix) if _zero_arg(c, 'kind') == 'simple_identifier'), None
                )
                if name_node and self._ts_node_text(name_node, content_bytes) in self._KOTLIN_VISIBLE_METHODS:
                    return True
            elif _zero_arg(callee, 'kind') == 'simple_identifier':
                if self._ts_node_text(callee, content_bytes) in self._KOTLIN_VISIBLE_METHODS:
                    return True
        return False

    # ── Swift (BACK-1011) ────────────────────────────────────────────────────

    def _check_swift(self, file_path: str, content: str) -> List[Detection]:
        """Check Swift source for silent broad `catch` clauses.

        Swift's `catch_block` (same node kind name as Kotlin's, unrelated
        grammar) narrows only when a `pattern` child actually types the
        catch — via `as SomeType` or an enum-case match like
        `MyError.specific` — to something other than `Error`/`NSError`. A
        bare `catch {}` or an untyped `catch let e` has no `pattern` (or a
        `pattern` with no type at all) and stays broad, same as an
        unqualified `catch` in the other languages.
        """
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._SWIFT_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')
        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'catch_block':
                continue
            if not self._swift_is_broad_catch(node, content_bytes):
                continue
            if self._swift_has_visible_signal(node, content_bytes):
                continue
            if any(_zero_arg(d, 'kind') == 'comment' for d in self._ts_walk(node)):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=_zero_arg(node, 'start_position').row + 1,
                column=_zero_arg(node, 'start_position').column + 1,
                suggestion=(
                    "Consider:\n"
                    "  1. Catch a specific error type: catch let e as SomeError\n"
                    "  2. Add visible logging: print(error) / logger.error(\"...\")\n"
                    "  3. Re-throw if you can't handle it: throw error"
                ),
                context=self._ts_node_text(node, content_bytes).split('\n')[0],
            ))

        return detections

    def _swift_is_broad_catch(self, node, content_bytes: bytes) -> bool:
        """True unless a `pattern` child types the catch to a non-broad type.

        Covers both `catch let e as SomeError` (an `as` type-cast pattern)
        and `catch SomeError.specific` (an enum-case match pattern) — both
        produce a `user_type` node somewhere inside `pattern`; an untyped
        `catch let e` binding produces a `pattern` with no `user_type` at
        all, which stays broad.
        """
        pattern = next((c for c in node_children(node) if _zero_arg(c, 'kind') == 'pattern'), None)
        if pattern is None:
            return True
        type_node = next((c for c in self._ts_walk(pattern) if _zero_arg(c, 'kind') == 'user_type'), None)
        if type_node is None:
            return True
        return self._ts_node_text(type_node, content_bytes) in self._SWIFT_BROAD_TYPES

    def _swift_has_visible_signal(self, node, content_bytes: bytes) -> bool:
        """True if the catch body re-throws or calls a visible print/log call."""
        statements = next((c for c in node_children(node) if _zero_arg(c, 'kind') == 'statements'), None)
        if statements is None:
            return False

        for descendant in self._ts_walk(statements):
            if _zero_arg(descendant, 'kind') == 'control_transfer_statement':
                first = node_children(descendant)
                if first and _zero_arg(first[0], 'kind') == 'throw_keyword':
                    return True
            if _zero_arg(descendant, 'kind') != 'call_expression':
                continue
            callee = node_children(descendant)[0] if node_children(descendant) else None
            if callee is None:
                continue
            if _zero_arg(callee, 'kind') == 'simple_identifier':
                if self._ts_node_text(callee, content_bytes) in self._SWIFT_VISIBLE_FUNCTIONS:
                    return True
            elif _zero_arg(callee, 'kind') == 'navigation_expression':
                suffix = next(
                    (c for c in node_children(callee) if _zero_arg(c, 'kind') == 'navigation_suffix'), None
                )
                if suffix is None:
                    continue
                name_node = next(
                    (c for c in node_children(suffix) if _zero_arg(c, 'kind') == 'simple_identifier'), None
                )
                if name_node and self._ts_node_text(name_node, content_bytes) in self._SWIFT_VISIBLE_METHODS:
                    return True
        return False

    def _check_cpp(self, file_path: str, content: str) -> List[Detection]:
        """Check C++ source for silent broad `catch` clauses."""
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._CPP_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')
        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'catch_clause':
                continue
            if not self._cpp_is_broad_catch(node, content_bytes):
                continue
            if self._cpp_has_visible_signal(node, content_bytes):
                continue
            if any(_zero_arg(d, 'kind') == 'comment' for d in self._ts_walk(node)):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=_zero_arg(node, 'start_position').row + 1,
                column=_zero_arg(node, 'start_position').column + 1,
                suggestion=(
                    "Consider:\n"
                    "  1. Catch specific exception types instead of std::exception/(...)\n"
                    "  2. Add visible output: std::cerr << \"...\" << e.what();\n"
                    "  3. Re-throw if you can't handle it: throw;"
                ),
                context=self._ts_node_text(node, content_bytes).split('\n')[0],
            ))

        return detections

    def _cpp_is_broad_catch(self, node, content_bytes: bytes) -> bool:
        """True for `catch (...)` (ellipsis, catches everything including
        non-exception types) or `catch (const std::exception& e)`.

        Ellipsis has no `parameter_declaration` child at all — just a bare
        `...` token directly under `parameter_list`.
        """
        param_list = next(
            (c for c in node_children(node) if _zero_arg(c, 'kind') == 'parameter_list'), None
        )
        if param_list is None:
            return False
        if any(_zero_arg(c, 'kind') == '...' for c in node_children(param_list)):
            return True

        declaration = next(
            (c for c in node_children(param_list) if _zero_arg(c, 'kind') == 'parameter_declaration'), None
        )
        if declaration is None:
            return False
        type_node = next(
            (c for c in node_children(declaration)
             if _zero_arg(c, 'kind') in ('type_identifier', 'qualified_identifier')),
            None
        )
        if type_node is None:
            return False
        type_name = self._ts_node_text(type_node, content_bytes).rsplit('::', 1)[-1]
        return type_name in self._CPP_BROAD_TYPES

    def _cpp_has_visible_signal(self, node, content_bytes: bytes) -> bool:
        """True if the catch body re-throws, streams to cerr/clog, or calls
        a visible stderr/logging function."""
        block = next((c for c in node_children(node) if _zero_arg(c, 'kind') == 'compound_statement'), None)
        if block is None:
            return False

        for descendant in self._ts_walk(block):
            kind = _zero_arg(descendant, 'kind')
            if kind == 'throw_statement':
                return True
            if kind in ('qualified_identifier', 'identifier'):
                if self._ts_node_text(descendant, content_bytes) in self._CPP_VISIBLE_STREAMS:
                    return True
            if kind == 'call_expression':
                if self._cpp_call_name(descendant, content_bytes) in (
                    self._CPP_VISIBLE_FUNCTIONS | self._CPP_VISIBLE_METHODS
                ):
                    return True
        return False

    def _cpp_call_name(self, node, content_bytes: bytes) -> Optional[str]:
        """Extract a `call_expression`'s callee name: the field/method name
        for `obj.method()`/`obj->method()` (`field_expression`), the last
        component for a namespaced call like `spdlog::error()`
        (`qualified_identifier`), or the bare name for a plain function
        call like `fprintf()`/`perror()` (`identifier`)."""
        children = node_children(node)
        callee = children[0] if children else None
        if callee is None:
            return None
        if _zero_arg(callee, 'kind') == 'field_expression':
            field = next(
                (c for c in node_children(callee) if _zero_arg(c, 'kind') == 'field_identifier'), None
            )
            return self._ts_node_text(field, content_bytes) if field else None
        if _zero_arg(callee, 'kind') == 'qualified_identifier':
            return self._ts_node_text(callee, content_bytes).rsplit('::', 1)[-1]
        if _zero_arg(callee, 'kind') == 'identifier':
            return self._ts_node_text(callee, content_bytes)
        return None
