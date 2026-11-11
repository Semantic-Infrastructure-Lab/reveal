#!/usr/bin/env python3
"""Import roots from native Hatchling editable wheels, without importing application code.

Only literal .pth paths are supported. Dynamic editable import hooks fail explicitly;
this is a bounded Hatchling oracle, not a fallback package-discovery implementation.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from importlib.metadata import version
from pathlib import Path


_BUILD = ('import sys; from hatchling.build import build_editable; '
          'print(build_editable(sys.argv[1]))')


def project_paths(root: Path, relative: str, output: Path) -> tuple[list[Path], dict]:
    project = (root / relative).resolve()
    if not relative or Path(relative).is_absolute() or not project.is_relative_to(root) or not project.is_dir():
        raise ValueError(f'Invalid build project: {relative!r}')
    metadata = project / 'pyproject.toml'
    config = tomllib.loads(metadata.read_text(encoding='utf-8'))
    if config.get('build-system', {}).get('build-backend') != 'hatchling.build':
        raise ValueError(f'Build project {relative!r} does not declare hatchling.build')
    result = subprocess.run([sys.executable, '-I', '-c', _BUILD, str(output)], cwd=project,
                            check=False, capture_output=True, text=True, encoding='utf-8', timeout=60)
    if result.returncode:
        raise RuntimeError(f'Hatch editable build failed for {relative}: {result.stderr.strip()}')
    wheel = output / result.stdout.strip()
    if wheel.parent != output or wheel.suffix != '.whl':
        raise ValueError(f'Unexpected editable wheel output for {relative}: {result.stdout!r}')
    paths = []
    with zipfile.ZipFile(wheel) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith('.pth'):
                continue
            for line in archive.read(name).decode('utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith(('import ', 'import\t')):
                    raise ValueError(f'Dynamic editable import hook is not supported: {relative}/{name}')
                path = Path(line).resolve()
                if not Path(line).is_absolute() or not path.is_relative_to(root) or not path.is_dir():
                    raise ValueError(f'Editable build root is not an existing corpus directory: {line!r}')
                if path not in paths:
                    paths.append(path)
    if not paths:
        raise ValueError(f'Hatch editable build produced no literal import roots for {relative}')
    inputs = [metadata] + ([project / 'hatch.toml'] if (project / 'hatch.toml').exists() else [])
    proof = {'project': project.relative_to(root).as_posix(),
             'roots': [path.relative_to(root).as_posix() for path in paths],
             'inputs': {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in inputs}}
    return paths, proof


def build_paths(root: Path, projects: list[str]) -> dict:
    if not projects or len(projects) != len(set(projects)):
        raise ValueError('build_projects must contain distinct project directories')
    roots, proof = [], []
    with tempfile.TemporaryDirectory(prefix='python-build-oracle-') as scratch:
        for index, project in enumerate(projects):
            output = Path(scratch) / str(index)
            output.mkdir()
            paths, record = project_paths(root, project, output)
            roots.extend(path for path in paths if path not in roots)
            proof.append(record)
    return {'roots': [path.relative_to(root).as_posix() for path in roots],
            'backend': 'hatchling.build', 'backend_version': version('hatchling'), 'editables_version': version('editables'), 'projects': proof}


def main() -> int:
    try:
        print(json.dumps(build_paths(Path(sys.argv[1]).resolve(), sys.argv[2:]), sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        print(f'Hatch build-path oracle failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
