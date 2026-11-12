"""One JSONL object reader with decisions bounded to the consumed record prefix."""
import json
from pathlib import Path


def valid_record_proof(proof):
    if not isinstance(proof, dict):
        return False
    keys = ('candidate_records', 'analyzed_records', 'failed_records')
    if not all(type(proof.get(key)) is int and proof[key] >= 0 for key in keys):
        return False
    if proof['candidate_records'] != proof['analyzed_records'] + proof['failed_records']:
        return False
    line = proof.get('first_failed_line')
    return (type(line) is int and line > 0) if proof['failed_records'] else line is None


class TranscriptRecords:
    def __init__(self, path: Path, *, replace_decode: bool = False):
        self.path, self.replace_decode = path, replace_decode
        self.candidates = self.analyzed = self.failed = self.recovered = 0
        self.first_failed: int | None = None
        self.failures: list[dict[str, str]] = []
        self.decision = 'interrupted'

    def _record(self, line, number):
        self.candidates += 1
        repaired = line.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
        if repaired != line:
            self.recovered += 1
        try:
            record = json.loads(repaired)
        except json.JSONDecodeError:
            record = None
        if isinstance(record, dict):
            self.analyzed += 1
            return record
        self.failed += 1
        self.first_failed = self.first_failed or number
        return None

    def records(self):
        errors = 'surrogateescape' if self.replace_decode else 'strict'
        try:
            with open(self.path, encoding='utf-8', errors=errors) as handle:
                for number, line in enumerate(handle, 1):
                    if line.strip():
                        record = self._record(line, number)
                        if record is not None:
                            yield record
            self.decision = 'exhausted'
        except (OSError, UnicodeDecodeError) as exc:
            self.failures.append({'phase': 'read', 'cause': type(exc).__name__, 'message': str(exc)})
            raise

    def record_proof(self):
        return {'candidate_records': self.candidates, 'analyzed_records': self.analyzed,
                'failed_records': self.failed, 'first_failed_line': self.first_failed}

    def receipt(self):
        return {**self.record_proof(), 'source': str(self.path), 'decision': self.decision,
                'recovered_records': self.recovered, 'failures': list(self.failures)}
