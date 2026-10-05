"""V033: shared composition behavioral contract (BACK-1660)."""
from ..base import BaseRule, RulePrefix, Severity
from .behavioral_contracts import composition_violations


class V033(BaseRule):
    code = 'V033'
    message = 'Shared composition contract violation'
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = []
    uri_patterns = ['^reveal://.*']
    internal = True

    def check(self, file_path, structure, content):
        return [self.create_detection(file_path, 1, message=message)
                for message in composition_violations()]
