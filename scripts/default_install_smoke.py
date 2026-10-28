#!/usr/bin/env python3
"""Run the README first-screen commands on a fresh core-only wheel install.

    python scripts/default_install_smoke.py
    python scripts/default_install_smoke.py --wheel dist/reveal_cli-*.whl

The invoking interpreter needs ``build`` when no wheel is supplied. The isolated
runtime receives only the wheel and its declared core dependencies, never [dev].
Network/package or grammar-download failures fail this CI step rather than skip it.
"""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import venv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.packaging_sources import stage_sources  # noqa: E402


class SmokeFailure(RuntimeError):
    """The installed package did not satisfy a documented workflow."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def clean_environment(root: Path) -> dict[str, str]:
    """Prevent editable-source imports and ambient Reveal settings in children."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('PYTHON', 'REVEAL_', 'GIT_'))}
    env.update(PYTHONNOUSERSITE='1', PYTHONIOENCODING='utf-8',
               REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(root / 'config'),
               REVEAL_CACHE_DIR=str(root / 'cache'), NO_COLOR='1', TERM='dumb')
    return env


def run(command: list[str], root: Path, env: dict[str, str], *,
        timeout: int = 90, expected: int = 0, label: str | None = None) -> subprocess.CompletedProcess:
    started = time.monotonic()
    result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=timeout)
    label = label or ' '.join(command)
    require(result.returncode == expected,
            f'{label}: expected exit {expected}, got exit {result.returncode}\n'
            f'{result.stdout}\n{result.stderr}')
    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    print(f'{stamp} PASS {label} [exit {result.returncode}] ({time.monotonic() - started:.1f}s)',
          flush=True)
    return result


def create_fixture(root: Path, env: dict[str, str]) -> None:
    """A real local history, caller and above-query-threshold complexity."""
    src = root / 'src'
    src.mkdir(parents=True)
    auth = src / 'auth.py'
    auth.write_text('"""Token validation."""\n\n\ndef validate_token(token: str) -> bool:\n'
                    '    """Accept a nonempty token."""\n    return bool(token)\n', encoding='utf-8')
    (src / 'login.py').write_text(
        '"""Login entry point."""\n\nfrom auth import validate_token\n\n\n'
        'def run_login(token: str) -> bool:\n    """Check one login."""\n'
        '    return validate_token(token)\n', encoding='utf-8')
    (src / 'complexity.py').write_text(
        '"""A bounded complexity-query fixture."""\n\n\n'
        'def classify(value: int) -> int:\n    """Map a small integer."""\n'
        + ''.join(f'    if value == {i}:\n        return {i}\n' for i in range(10))
        + '    return -1\n', encoding='utf-8')
    # The query still finds complexity 11; this project's policy permits up to 20.
    (root / '.reveal.yaml').write_text('rules:\n  C901:\n    threshold: 20\n', encoding='utf-8')
    git = ['git', '-c', 'user.name=smoke', '-c', 'user.email=smoke@example.invalid',
           '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=']
    for args in (['init', '-q', '-b', 'main'], ['add', 'src', '.reveal.yaml'],
                 ['commit', '-q', '-m', 'fixture base'], ['switch', '-q', '-c', 'smoke-change']):
        run(git + args, root, env)
    auth.write_text(auth.read_text(encoding='utf-8').replace('bool(token)', 'token == "accepted"'),
                    encoding='utf-8')
    run(git + ['add', 'src/auth.py'], root, env)
    run(git + ['commit', '-q', '-m', 'change token validation'], root, env)


def validate_overview(result: subprocess.CompletedProcess) -> dict:
    """The regression assertion: absent pygit2 is visible and not exit 3."""
    require(result.returncode == 0, f'overview: expected exit 0, got exit {result.returncode}')
    answer = json.loads(result.stdout)
    meta = answer.get('meta') or {}
    require(not meta.get('errors'), 'overview: unexpected analysis errors')
    warnings = [w for w in meta.get('warnings', []) if w.get('type') == 'git_unavailable']
    require(len(warnings) == 1, 'overview: expected one git_unavailable warning')
    require('reveal-cli[git]' in warnings[0].get('message', ''), 'overview: missing install hint')
    return answer


def installed_identity(python: Path, root: Path, env: dict[str, str]) -> dict:
    """Prove this is the wheel, not the source tree or an editable installation."""
    probe = (
        'import importlib.util, importlib.metadata, json, pathlib, sys; import reveal; '
        'dist = importlib.metadata.distribution("reveal-cli"); '
        'print(json.dumps({"module": str(pathlib.Path(reveal.__file__).resolve()), '
        '"prefix": sys.prefix, "pygit2": importlib.util.find_spec("pygit2") is not None, '
        '"pytest": importlib.util.find_spec("pytest") is not None, '
        '"direct_url": json.loads(dist.read_text("direct_url.json") or "{}")}))'
    )
    result = run([str(python), '-I', '-c', probe], root, env, label='installed-wheel identity probe')
    identity = json.loads(result.stdout)
    require(Path(identity['module']).is_relative_to(Path(identity['prefix']).resolve()),
            'reveal imported outside the isolated venv')
    require(not identity['pygit2'] and not identity['pytest'], 'runtime contains optional/dev extras')
    direct = identity['direct_url']
    require(direct.get('url', '').endswith('.whl') and 'dir_info' not in direct,
            'runtime was not installed from a wheel')
    print(f'Installed wheel identity: {json.dumps(identity, sort_keys=True)}', flush=True)
    return identity


def readme_commands(path: Path) -> list[tuple[str, ...]]:
    """Read the first bash block; unsupported/new examples must get a fixture."""
    block = path.read_text(encoding='utf-8').partition('```bash\n')[2].partition('```')[0]
    require(bool(block), 'README has no first-screen bash examples')
    commands = []
    for line in block.split('\n'):
        argv = shlex.split(line, comments=True)
        if argv:
            require(argv[0] == 'reveal', 'README first-screen example needs a smoke fixture')
            commands.append(tuple(argv[1:]))
    return commands


def smoke_commands(cli: Path, root: Path, env: dict[str, str]) -> None:
    """Run the documented text commands, then verify their structured answers."""
    prefix = [str(cli)]
    examples = {
        ('src/auth.py', 'validate_token'): 'return token == "accepted"',
        ('calls://src/?callers=validate_token',): 'run_login',
        ('overview', '.'): 'reveal-cli[git]',
        ('ast://src/?complexity>10',): 'classify',
        ('check', 'src/'): 'No issues found',
        ('pack', 'src/', '--since', 'main', '--budget', '8000'): 'auth.py',
    }
    commands = readme_commands(Path(__file__).resolve().parent.parent / 'README.md')
    require(len(commands) == len(examples) and set(commands) == set(examples),
            'README first-screen commands changed; update the smoke fixtures and expected answers')
    for args in commands:
        result = run(prefix + list(args), root, env)
        require(examples[args] in result.stdout, f'{args}: expected {examples[args]!r} in text answer')
    overview = run(prefix + ['overview', '.', '--format', 'json'], root, env)
    dashboard = validate_overview(overview)
    require(dashboard['scope']['total_code_files'] == 3
            and dashboard['stats']['summary']['total_functions'] == 3,
            'overview: fixture files/functions are missing')
    calls = json.loads(run(prefix + ['calls://src/?callers=validate_token', '--format', 'json'],
                           root, env).stdout)
    ast = json.loads(run(prefix + ['ast://src/?complexity>10', '--format', 'json'], root, env).stdout)
    validate_queries(calls, ast)
    packed = json.loads(run(prefix + ['pack', 'src/', '--since', 'main', '--budget', '8000',
                                     '--format', 'json'], root, env).stdout)
    require(packed['since'] == 'main' and packed['meta']['changed_files_count'] == 1,
            'pack: changed-file selection did not use main history')
    require(not packed['meta'].get('since_error'), 'pack: since analysis silently failed')
    require(any(row['path'].endswith('auth.py') for row in packed['files']),
            'pack: changed auth.py missing from selected files')
    _check_findings(cli, root, env)


def validate_queries(calls: dict, ast: dict) -> None:
    require(not calls.get('meta', {}).get('errors') and not ast.get('meta', {}).get('errors'),
            'calls/ast: unexpected analysis errors')
    require(calls['total_callers'] == 1
            and [(row['file'], row['caller']) for row in calls['levels'][0]['callers']]
            == [('src/login.py', 'run_login')], 'calls: expected the one real login caller')
    require(ast['total_results'] == 1
            and [(row['file'], row['name'], row['complexity']) for row in ast['results']]
            == [('src/complexity.py', 'classify', 11)], 'ast: expected the complexity-11 function')


def _check_findings(cli: Path, root: Path, env: dict[str, str]) -> None:
    """A clean scan and a deliberately introduced C901 finding have distinct exits."""
    args = [str(cli), 'check', 'src/', '--select', 'C901', '--format', 'json']
    clean = json.loads(run(args, root, env).stdout)
    require(clean['summary']['total_issues'] == 0, 'check: clean scan contains findings')
    bad = root / 'src' / 'too_complex.py'
    bad.write_text('def too_complex(value):\n'
                   + ''.join(f'    if value == {i}:\n        return {i}\n' for i in range(25))
                   + '    return -1\n', encoding='utf-8')
    try:
        findings = json.loads(run(args, root, env, expected=1).stdout)
        require(findings['summary']['total_issues'] == 1, 'check: expected exactly one C901 finding')
    finally:
        bad.unlink()


def verify_regression_control(identity: dict, cli: Path, root: Path, env: dict[str, str]) -> None:
    """Temporarily restore the missing-pygit2 failure in the installed copy only."""
    overview = Path(identity['module']).parent / 'adapters' / 'overview.py'
    original = overview.read_text(encoding='utf-8')
    guard = 'unavailable = _git_unavailable_warning()'
    require(original.count(guard) == 1, 'regression control: missing optional-git guard changed')
    sibling = [str(cli), 'src/auth.py', 'validate_token']
    before = run(sibling, root, env).stdout
    args = [str(cli), 'overview', '.', '--format', 'json']
    try:
        # Skipping this check reaches the old GitAdapter ImportError -> E_COMPOSE path.
        overview.write_text(original.replace(guard, 'unavailable = None'), encoding='utf-8')
        failed = run(args, root, env, expected=3)
        errors = json.loads(failed.stdout).get('meta', {}).get('errors', [])
        require(any(error.get('code') == 'E_COMPOSE' for error in errors),
                'regression control did not restore the historical composed failure')
        try:
            validate_overview(failed)
        except SmokeFailure as exc:
            print(f'PASS regression control rejected by validate_overview: {exc}', flush=True)
        else:
            raise SmokeFailure('regression control: smoke accepted failed overview')
        require(run(sibling, root, env).stdout == before, 'regression control changed unrelated extraction')
    finally:
        overview.write_text(original, encoding='utf-8')
    validate_overview(run(args, root, env))


def build_wheel(project: Path, root: Path, env: dict[str, str]) -> Path:
    stage = root / 'source'
    stage_sources(project, stage)
    out = root / 'dist'
    run([sys.executable, '-m', 'build', '--wheel', '--outdir', str(out)], stage, env, timeout=600)
    wheels = list(out.glob('*.whl'))
    require(len(wheels) == 1, 'build did not produce exactly one wheel')
    return wheels[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, help='install an already-built wheel instead of building')
    parser.add_argument('--verify-regression-control', action='store_true',
                        help='prove the smoke catches the old missing-pygit2 overview failure')
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='reveal-default-install-') as tmp:
        root = Path(tmp).resolve()
        env = clean_environment(root)
        wheel = args.wheel.resolve() if args.wheel else build_wheel(Path(__file__).resolve().parent.parent,
                                                                  root, env)
        runtime = root / 'runtime'
        venv.EnvBuilder(with_pip=True).create(runtime)
        scripts = runtime / ('Scripts' if os.name == 'nt' else 'bin')
        python = scripts / ('python.exe' if os.name == 'nt' else 'python')
        cli = scripts / ('reveal.exe' if os.name == 'nt' else 'reveal')
        run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', str(wheel)],
            root, env, timeout=600)
        identity = installed_identity(python, root, env)
        fixture = root / 'fixture'
        create_fixture(fixture, env)
        smoke_commands(cli, fixture, env)
        if args.verify_regression_control:
            verify_regression_control(identity, cli, fixture, env)
    print('PASS default-install smoke: README commands, optional-dependency disclosure, findings control',
          flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
