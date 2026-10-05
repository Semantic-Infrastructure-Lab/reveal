"""V034: shared pagination behavioral contract (BACK-1660)."""
from ..base import BaseRule, RulePrefix, Severity
from .behavioral_contracts import pagination_violations


class V034(BaseRule):
    code = 'V034'
    message = 'Shared pagination contract violation'
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = []
    uri_patterns = ['^reveal://.*']
    internal = True

    def check(self, file_path, structure, content):
        return [self.create_detection(file_path, 1, message=message)
                for message in pagination_violations()]
