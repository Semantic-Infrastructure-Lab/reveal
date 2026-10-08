"""scripts/check_changelog_coverage.py: which commits it holds to a CHANGELOG entry."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'check_changelog_coverage.py'
spec = importlib.util.spec_from_file_location('check_changelog_coverage', SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_only_feat_fix_perf_are_held_to_an_entry():
    for subject in ('fix: x', 'fix(git): x', 'feat(rules)!: x', 'perf(stats): x'):
        assert gate.USER_VISIBLE.match(subject), subject
    for subject in ('test: x', 'docs(roadmap): x', 'refactor(a): x', 'ci: x', 'fixture: x'):
        assert not gate.USER_VISIBLE.match(subject), subject


def test_missing_ids_are_reported_and_covered_ones_are_not(monkeypatch):
    log = ('aaa fix(git): one (BACK-1)\nbbb fix(cli): two (BACK-2, BACK-3)\n'
           'ccc test: three (BACK-4)\nddd fix: no id here\n')
    monkeypatch.setattr(gate, '_git', lambda *a: log)
    monkeypatch.setattr(gate, 'unreleased_section', lambda since=None: 'BACK-1 is described; BACK-3 too')
    monkeypatch.setattr(gate, 'skipped_ids', lambda: set())
    missing, idless = gate.uncovered('v0')
    assert list(missing) == ['BACK-2']
    assert idless == ['ddd fix: no id here']

