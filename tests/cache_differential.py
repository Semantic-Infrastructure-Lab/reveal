"""Shared steps of the cache differential harnesses (BACK-2081, step 5).

Each harness asks one request as separate processes through the public path, with the disk
cache switched explicitly on or off (never the ambient environment, BACK-1677), and compares the
answers after dropping what legitimately differs between two runs. Used by every
``test_*_differential_back2081.py`` harness.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from reveal.utils.path_utils import to_posix

VOLATILE = frozenset({'elapsed', 'elapsed_ms', 'duration', 'duration_ms', 'timing', 'timings', 'cache',
                      'cache_hit', 'from_cache', 'generated_at', 'perf'})


def comparable(value: Any) -> Any:
    """The answer without what legitimately differs between two runs (timings, cache provenance)."""
    if isinstance(value, dict):
        return {k: comparable(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [comparable(v) for v in value]
    return value


def cache_env(cache_dir: Path, *, cache: bool) -> Dict[str, str]:
    """The environment of one harness process: no user config, the disk cache set explicitly."""
    return {**os.environ, 'PYTHONHASHSEED': '0', 'REVEAL_NO_CONFIG': '1',
            'REVEAL_CACHE_DIR': str(cache_dir), 'REVEAL_DISK_CACHE': '1' if cache else '0'}


def run_reveal(argv: Sequence[str], cache_dir: Path, *, cache: bool, cwd: Optional[Path] = None,
               as_json: bool = True, ok_codes: Tuple[int, ...] = (0, 3)) -> Tuple[int, Any]:
    """One ``reveal`` request in its own process: (exit code, comparable answer).

    The answer is the parsed JSON with ``VOLATILE`` keys dropped, or the stdout text when
    *as_json* is false (a text-only view such as ``--outline``).
    """
    done = subprocess.run([sys.executable, '-m', 'reveal', *argv], cwd=cwd, capture_output=True,
                          text=True, encoding='utf-8', env=cache_env(cache_dir, cache=cache), timeout=120)
    assert done.returncode in ok_codes, done.stderr
    return done.returncode, comparable(json.loads(done.stdout)) if as_json else done.stdout


def cache_entries(cache_dir: Path) -> Dict[str, Tuple[int, int]]:
    """Every stored entry under *cache_dir* with its (size, mtime_ns).

    A miss rebuilds and re-stores its entry, so an unchanged map across a run means the run
    stored nothing: every entry it needed was read back.
    """
    if not cache_dir.exists():
        return {}
    return {to_posix(path.relative_to(cache_dir)): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in cache_dir.rglob('*') if path.is_file()}


# A long-lived library host: each ``reveal.api.query`` is one host request (request_cache.host_request),
# so the validated in-memory caches live across the steps and must notice the edits made between them.
HOST_DRIVER = r'''
import json, sys
from pathlib import Path
from reveal.api import query
plan = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
answers = []
for step in plan['steps']:
    for rel, text in step:
        path = Path(rel)
        if text is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
    answers.append({view: query(uri) for view, uri in plan['views'].items()})
sys.stdout.write(json.dumps(answers, default=str, sort_keys=True))
'''


def run_host(root: Path, views: Dict[str, str], steps: List[List[Tuple[str, Optional[str]]]],
             cache_dir: Path, *, cache: bool) -> List[Dict[str, Any]]:
    """Run *steps* in ONE process with cwd *root*: apply a step's edits (relative path, new text or
    None to delete), then answer every view through ``reveal.api.query``. One answer map per step."""
    plan = root.parent / f'{root.name}-plan.json'
    plan.write_text(json.dumps({'views': views, 'steps': steps}), encoding='utf-8')
    done = subprocess.run([sys.executable, '-c', HOST_DRIVER, str(plan)], cwd=root, capture_output=True,
                          text=True, encoding='utf-8', env=cache_env(cache_dir, cache=cache), timeout=300)
    assert done.returncode == 0, done.stderr
    return comparable(json.loads(done.stdout))
