"""The shipped first-screen examples must stay covered by the wheel smoke."""
from pathlib import Path

from scripts.default_install_smoke import readme_commands


def test_shipped_readme_first_screen_has_qualified_fixture_plan():
    assert readme_commands(Path(__file__).resolve().parents[1] / 'README.md') == [
        ('src/',), ('src/app.py',), ('src/app.py', 'main'),
        ('calls', 'src/', '--callers', 'main'),
        ('src/app.py', 'main', '--boundary'), ('check', 'src/'),
    ]


def test_current_readme_answers_and_deeper_controls(tmp_path, monkeypatch):
    import subprocess
    from conftest import _run_reveal_in
    from scripts import default_install_smoke as smoke
    root = tmp_path / 'fixture'
    env = smoke.clean_environment(tmp_path)
    smoke.create_fixture(root, env)

    def local_run(command, cwd, env, *, expected=0, **kwargs):
        result = _run_reveal_in(cwd, *command[1:])
        assert result.returncode == expected, (command, result.stdout, result.stderr)
        return subprocess.CompletedProcess(command, result.returncode, result.stdout, result.stderr)

    monkeypatch.setattr(smoke, 'run', local_run)
    smoke.smoke_commands(Path('reveal'), root, env)


def test_install_setup_exception_does_not_skip_unknown_commands(tmp_path):
    import pytest
    from scripts.default_install_smoke import SmokeFailure
    readme = tmp_path / 'README.md'
    readme.write_text('```bash\npip install unexpected-package\nreveal src/\n```\n', encoding='utf-8')
    with pytest.raises(SmokeFailure, match='needs a smoke fixture'):
        readme_commands(readme)
