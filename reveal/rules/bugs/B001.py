"""B001: Bare except clause detector.

Detects bare except clauses in Python that catch all exceptions including
SystemExit, plus the C#/C++ analog: a catch with no type at all (`catch { }`
in C#, `catch (...)` in C++) — unlike Python's `except:`, these languages
don't have a SystemExit/KeyboardInterrupt-equivalent, but a completely
untyped catch still masks what was actually thrown (in C++, `catch (...)`
catches non-exception-derived thrown values too, which `.what()` can't even
be called on) independent of whether the handler happens to log something.
That's a distinct, narrower finding than B006 (broad-but-typed catch with no
visible signal) — B001 fires on the catch's *type shape* regardless of body
content, exactly as it does in Python. See BACK-1011 note #1.
"""

import ast
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin, TreeSitterParsingMixin
from ...core import node_children, _zero_arg


class B001(BaseRule, ASTParsingMixin, TreeSitterParsingMixin):
    """Detect bare/untyped except-all catch clauses."""

    code = "B001"
    message = "Bare except clause catches all exceptions including SystemExit"
    category = RulePrefix.B
    severity = Severity.HIGH
    file_patterns = ['.py', '.cs', '.cpp', '.cc', '.cxx', '.hpp', '.hh', '.h++']
    version = "1.1.0"

    _CS_LANGUAGE = 'csharp'
    _CPP_LANGUAGE = 'cpp'

    @staticmethod
    def _get_except_context(content: str, node) -> Optional[str]:
        """Return the first line of an except handler's source."""
        try:
            src = ast.get_source_segment(content, node)
            return src.split('\n')[0] if src else None
        except Exception:
            return None

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for bare/untyped except-all catch clauses.

        Args:
            file_path: Path to source file
            structure: Parsed structure (not used, we parse ourselves)
            content: File content

        Returns:
            List of detections
        """
        if file_path.endswith('.cs'):
            return self._check_csharp(file_path, content)
        if file_path.endswith(('.cpp', '.cc', '.cxx', '.hpp', '.hh', '.h++')):
            return self._check_cpp(file_path, content)

        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        # Walk the AST looking for bare except handlers
        for node in self._ast_walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                context = self._get_except_context(content, node)
                detections.append(self.create_detection(
                        file_path=file_path,
                        line=node.lineno,
                        column=node.col_offset + 1,  # AST is 0-indexed, display is 1-indexed
                        suggestion="Use 'except Exception:' or specific exception types (ValueError, IOError, etc.)",
                        context=context
                    ))

        return detections

    # ── C# (BACK-1011) ───────────────────────────────────────────────────────

    def _check_csharp(self, file_path: str, content: str) -> List[Detection]:
        """Check C# source for a bare `catch { }` — no `catch_declaration` at
        all, so no exception type is named anywhere in the clause."""
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._CS_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')
        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'catch_clause':
                continue
            if any(_zero_arg(c, 'kind') == 'catch_declaration' for c in node_children(node)):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=node.start_position().row + 1,
                column=node.start_position().column + 1,
                message="Bare 'catch { }' names no exception type, catching everything",
                suggestion="Catch a specific exception type instead of a bare 'catch { }'.",
                context=self._ts_node_text(node, content_bytes).split('\n')[0],
            ))

        return detections

    # ── C++ (BACK-1011) ──────────────────────────────────────────────────────

    def _check_cpp(self, file_path: str, content: str) -> List[Detection]:
        """Check C++ source for `catch (...)` — the ellipsis handler, which
        catches literally anything thrown (including non-exception-derived
        values `.what()` can't be called on), not just `std::exception` and
        its subtypes."""
        root, detections = self._parse_treesitter_or_skip(content, file_path, self._CPP_LANGUAGE)
        if root is None:
            return detections

        content_bytes = content.encode('utf-8')
        for node in self._ts_walk(root):
            if _zero_arg(node, 'kind') != 'catch_clause':
                continue
            param_list = next(
                (c for c in node_children(node) if _zero_arg(c, 'kind') == 'parameter_list'), None
            )
            if param_list is None:
                continue
            if not any(_zero_arg(c, 'kind') == '...' for c in node_children(param_list)):
                continue

            detections.append(self.create_detection(
                file_path=file_path,
                line=node.start_position().row + 1,
                column=node.start_position().column + 1,
                message="'catch (...)' catches everything, including non-exception thrown values",
                suggestion="Catch std::exception (or a specific type) instead of 'catch (...)'.",
                context=self._ts_node_text(node, content_bytes).split('\n')[0],
            ))

        return detections
