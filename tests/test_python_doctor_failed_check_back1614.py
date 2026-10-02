"""BACK-1614: a doctor check that crashes is reported, not read as "nothing found"."""

from reveal.adapters.python import doctor


def _no_venv():
    return {'active': True, 'path': '/venv', 'type': 'venv'}


def test_crashed_check_is_a_warning_and_listed_as_failed(monkeypatch):
    def _boom():
        raise RuntimeError('metadata scan broke')

    monkeypatch.setattr(doctor, 'check_package_dir_shadowing', _boom)
    result = doctor.run_doctor(_no_venv)
    assert result['checks_failed'] == ['package_dir_shadowing']
    assert 'package_dir_shadowing' not in result['checks_performed']
    assert 'stale_bytecode' in result['checks_performed']  # the rest still ran
    assert any(w['message'] == 'The package_dir_shadowing check could not run '
                               '(RuntimeError: metadata scan broke)' for w in result['warnings'])


def test_clean_run_has_no_failed_checks():
    result = doctor.run_doctor(_no_venv)
    assert 'checks_failed' not in result
    assert len(result['checks_performed']) == 7
