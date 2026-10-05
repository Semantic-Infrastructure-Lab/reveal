"""V035: shared renderer diagnostics behavioral contract (BACK-1660)."""
from ..base import BaseRule, RulePrefix, Severity
from .behavioral_contracts import renderer_violations


class V035(BaseRule):
    code = 'V035'
    message = 'Shared renderer diagnostics contract violation'
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = []
    uri_patterns = ['^reveal://.*']
    internal = True

    def check(self, file_path, structure, content):
        return [self.create_detection(file_path, 1, message=message)
                for message in renderer_violations()]
