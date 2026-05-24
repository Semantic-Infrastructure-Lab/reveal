"""S001: Hardcoded secrets detector.

Detects string literals that look like real secrets assigned to
secret-like variable names. Covers Python, .env, YAML, and TOML files.
"""

import ast
import re
import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin

logger = logging.getLogger(__name__)

# Variable name patterns that suggest a secret value
_SECRET_NAME_RE = re.compile(
    r'(password|passwd|secret|api.?key|apikey|token|credential|auth.?key|'
    r'private.?key|access.?key|client.?secret|signing.?key|encryption.?key)',
    re.IGNORECASE,
)

# Value prefixes that are unambiguously real secrets
_KNOWN_SECRET_PREFIXES = (
    'sk-proj-', 'sk-ant-', 'sk-',   # Anthropic / OpenAI
    'ghp_', 'ghs_', 'gho_',          # GitHub tokens
    'AKIA', 'ASIA',                   # AWS access keys
    'xoxb-', 'xoxp-', 'xoxa-',       # Slack tokens
    'eyJ',                            # JWT (base64 header)
    'glpat-',                         # GitLab PAT
    'npm_',                           # npm tokens
    'ya29.',                          # Google OAuth
)

# Values that are clearly not real secrets
_SAFE_VALUE_RE = re.compile(
    r'^('
    r'<[^>]*>'              # <placeholder>, <YOUR_KEY>, etc.
    r'|\$\{[^}]*\}'         # ${ENV_VAR}
    r'|\$[A-Z_]+'           # $ENV_VAR
    r'|%\([^)]*\)s'         # %(env_var)s
    r'|your[-_]'            # your-secret, your_token
    r'|\*+$'                # *** or ****
    r')$',
    re.IGNORECASE,
)

_SAFE_VALUE_WORDS = frozenset({
    'test', 'example', 'placeholder', 'dummy', 'fake', 'sample',
    'none', 'null', 'todo', 'fixme', 'changeme', 'replace_me',
    'replace-me', 'insert_here', 'insert-here', 'notset', 'not-set',
    'not_set', 'development', 'undefined',
})

_MIN_VALUE_LENGTH = 6


class S001(BaseRule, ASTParsingMixin):
    """Detect hardcoded secrets in source files."""

    code = "S001"
    message = "Hardcoded secret — move to environment variable or secrets manager"
    category = RulePrefix.S
    severity = Severity.HIGH
    file_patterns = ['.py', '.env', '.yaml', '.yml', '.toml']
    version = "1.0.0"

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        ext = self._ext(file_path)
        if ext == '.py':
            return self._check_python(file_path, content)
        if ext in ('.yaml', '.yml'):
            return self._check_yaml(file_path, content)
        if ext == '.toml':
            return self._check_toml(file_path, content)
        if self._is_env_file(file_path):
            return self._check_env(file_path, content)
        return []

    # ------------------------------------------------------------------
    # Python: AST-based assignment detection
    # ------------------------------------------------------------------

    def _check_python(self, file_path: str, content: str) -> List[Detection]:
        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        for node in self._ast_walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        det = self._check_name_value(
                            file_path, target.id, node.value,
                            node.lineno, node.col_offset + 1,
                        )
                        if det:
                            detections.append(det)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.value is not None:
                    det = self._check_name_value(
                        file_path, node.target.id, node.value,
                        node.lineno, node.col_offset + 1,
                    )
                    if det:
                        detections.append(det)

        return detections

    def _check_name_value(
        self,
        file_path: str,
        name: str,
        value_node: ast.expr,
        lineno: int,
        col: int,
    ) -> Optional[Detection]:
        if not _SECRET_NAME_RE.search(name):
            return None
        if not isinstance(value_node, ast.Constant) or not isinstance(value_node.value, str):
            return None
        value = value_node.value
        if not self._looks_like_secret(value):
            return None
        return self.create_detection(
            file_path=file_path,
            line=lineno,
            column=col,
            message=f"{self.message}: {name}",
            suggestion="Use os.environ.get('...') or a secrets manager",
            context=f"{name} = {self._redact(value)}",
        )

    # ------------------------------------------------------------------
    # Non-Python: line-by-line regex
    # ------------------------------------------------------------------

    _ENV_LINE_RE = re.compile(r'^([A-Z0-9_]+)\s*=\s*(.+)$')
    _YAML_LINE_RE = re.compile(r'^(\s*)([a-zA-Z0-9_.-]+)\s*:\s*["\']?([^#\n"\']+)["\']?\s*(?:#.*)?$')
    _TOML_LINE_RE = re.compile(r'^([a-zA-Z0-9_.-]+)\s*=\s*["\']([^"\']+)["\']')

    def _check_env(self, file_path: str, content: str) -> List[Detection]:
        detections = []
        for i, line in enumerate(content.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = self._ENV_LINE_RE.match(line)
            if m and _SECRET_NAME_RE.search(m.group(1)) and self._looks_like_secret(m.group(2).strip()):
                detections.append(self.create_detection(
                    file_path=file_path, line=i, column=1,
                    message=f"{self.message}: {m.group(1)}",
                    suggestion="Reference via shell environment or secrets manager, not literal value",
                    context=f"{m.group(1)}={self._redact(m.group(2).strip())}",
                ))
        return detections

    def _check_yaml(self, file_path: str, content: str) -> List[Detection]:
        detections = []
        for i, line in enumerate(content.splitlines(), start=1):
            if not line.strip() or line.strip().startswith('#'):
                continue
            m = self._YAML_LINE_RE.match(line)
            if m and _SECRET_NAME_RE.search(m.group(2)) and self._looks_like_secret(m.group(3).strip()):
                detections.append(self.create_detection(
                    file_path=file_path, line=i, column=len(m.group(1)) + 1,
                    message=f"{self.message}: {m.group(2)}",
                    suggestion="Use an environment variable reference or secrets injection",
                    context=f"{m.group(2)}: {self._redact(m.group(3).strip())}",
                ))
        return detections

    def _check_toml(self, file_path: str, content: str) -> List[Detection]:
        detections = []
        for i, line in enumerate(content.splitlines(), start=1):
            if not line.strip() or line.strip().startswith('#'):
                continue
            m = self._TOML_LINE_RE.match(line.strip())
            if m and _SECRET_NAME_RE.search(m.group(1)) and self._looks_like_secret(m.group(2)):
                detections.append(self.create_detection(
                    file_path=file_path, line=i, column=1,
                    message=f"{self.message}: {m.group(1)}",
                    suggestion="Use an environment variable reference",
                    context=f"{m.group(1)} = {self._redact(m.group(2))}",
                ))
        return detections

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _looks_like_secret(self, value: str) -> bool:
        """Return True if value appears to be a real secret, not a placeholder."""
        # Always flag known-bad prefixes regardless of length
        if value.startswith(_KNOWN_SECRET_PREFIXES):
            return True
        # Skip clearly safe patterns
        if _SAFE_VALUE_RE.match(value):
            return False
        # Skip very short values (real secrets are at least 6 chars)
        if len(value) < _MIN_VALUE_LENGTH:
            return False
        # Skip known placeholder words
        if value.lower() in _SAFE_VALUE_WORDS:
            return False
        if any(word in value.lower() for word in ('example', 'placeholder', 'your_', 'your-', 'dummy', 'fake')):
            return False
        return True

    def _redact(self, value: str) -> str:
        if len(value) <= 4:
            return '***'
        return value[:2] + '***' + value[-2:]

    @staticmethod
    def _ext(file_path: str) -> str:
        from pathlib import Path
        return Path(file_path).suffix.lower()

    @staticmethod
    def _is_env_file(file_path: str) -> bool:
        from pathlib import Path
        name = Path(file_path).name
        return name == '.env' or name.startswith('.env.') or name.endswith('.env')
