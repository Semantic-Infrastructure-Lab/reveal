"""Measured document acquisition stages shared by structured configuration readers."""
from contextlib import contextmanager
from typing import Any, Dict

from .results import note_warning


class DocumentRead:
    def __init__(self, path, *, label='installation JSON'):
        self.path, self.label = path, label
        self.selected = self.parsed = self.usable = False
        self.operations: list[Dict[str, Any]] = []

    @contextmanager
    def operation(self, phase, *, missing_request=False):
        try:
            yield
        except (OSError, ValueError) as exc:
            self.error(phase, exc, rejected=missing_request and isinstance(exc, FileNotFoundError))
            raise
        else:
            self.operations.append({'phase': phase, 'outcome': 'ok'})

    def select(self):
        with self.operation('select', missing_request=True):
            self.path.stat()
        self.selected = True

    def error(self, phase, exc, *, rejected=False):
        self.operations.append({'phase': phase, 'outcome': 'rejected' if rejected else 'failed',
                                'cause': type(exc).__name__, 'message': str(exc)})

    def repair(self, text):
        with self.operation('decode'):
            repaired = text.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
        if repaired != text:
            self.operations[-1]['outcome'] = 'recovered'
            self.operations[-1]['message'] = 'Invalid UTF-8 bytes replaced using the existing config codec'
        return repaired

    def attach(self, result: Dict[str, Any]) -> Dict[str, Any]:
        states = [op['outcome'] for op in self.operations]
        proof = {'source': str(self.path), 'selected': self.selected, 'parsed': self.parsed,
                 'usable': self.usable, 'failed_operations': states.count('failed'),
                 'recovered_operations': states.count('recovered'),
                 'request_rejected': 'rejected' in states, 'operations': list(self.operations),
                 'count_rule': 'Authored selection/read/parse/decode stages and failed key/root validation; not syscall counts or universal payload validation'}
        result.setdefault('meta', {})['installation_analysis'] = proof
        if proof['request_rejected']:
            result['meta'].setdefault('errors', []).append({'code': 'invalid_request', 'message': result.get('error') or next(op['message'] for op in self.operations if op['outcome'] == 'rejected')})
        if proof['failed_operations'] or proof['recovered_operations']:
            note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete',
                                  'field': 'installation_analysis',
                                  'message': f'Required {self.label} input was lost or repaired. Decisions: JSON meta.installation_analysis.'})
        return result



def document_proof_error(proof, *, label='Document'):
    if not isinstance(proof, dict):
        return f'{label} answer missing source decisions'
    if not all(type(proof.get(k)) is bool for k in ('selected', 'parsed', 'usable', 'request_rejected')):
        return f'{label} answer missing source states'
    if (proof['usable'] and not proof['parsed']) or (proof['parsed'] and not proof['selected']):
        return f'{label} source states are inconsistent'
    operations = proof.get('operations')
    if not isinstance(operations, list) or not operations:
        return f'{label} answer missing acquisition stages'
    if not all(isinstance(op, dict) and op.get('outcome') in ('ok', 'failed', 'recovered', 'rejected')
               and isinstance(op.get('phase'), str) for op in operations):
        return f'{label} acquisition stages are inconsistent'
    return _counts_error(proof, operations, label)


def _counts_error(proof, operations, label):
    states = [op['outcome'] for op in operations]
    for key, state in (('failed_operations', 'failed'), ('recovered_operations', 'recovered')):
        if type(proof.get(key)) is not int or proof[key] != states.count(state):
            return f'{label} counts disagree with acquisition stages'
    if proof['request_rejected'] != ('rejected' in states):
        return f'{label} request state disagrees with acquisition stages'
    return None
