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



def _bullets(count, text='A short user-facing entry (BACK-1).'):
    return ''.join(f'- {text}\n' for _ in range(count))


def test_an_overlong_entry_is_an_error():
    errors, _ = gate.style_problems('### Fixed\n- ' + 'x' * (gate.MAX_ENTRY_CHARS + 1) + '\n')
    assert len(errors) == 1 and 'too long' in errors[0]


def test_an_entry_at_the_limit_and_a_clean_section_pass():
    errors, warnings = gate.style_problems('### Fixed\n- ' + 'x' * (gate.MAX_ENTRY_CHARS - 2) + '\n' + _bullets(3))
    assert errors == [] and warnings == []


def test_an_oversized_section_is_an_error():
    one = len(_bullets(1).encode())
    errors, _ = gate.style_problems(_bullets(gate.MAX_SECTION_KB * 1024 // one + 1))
    assert any('section is' in e for e in errors)


def test_internal_vocabulary_is_a_warning_not_an_error():
    errors, warnings = gate.style_problems('- Pack retains candidate failures before the carrier cut (BACK-2).\n')
    assert errors == [] and len(warnings) == 1 and 'retains' in warnings[0]


def test_wrapped_continuation_lines_do_not_count_as_new_entries():
    errors, _ = gate.style_problems('- short entry\n  continuation of the same entry\n')
    assert errors == []
