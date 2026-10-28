"""Deterministic per-file import extraction and optional structure collection."""
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...utils.parallel import pool_worker_count, submit_each
from . import resolution
from .base import get_extractor
from .types import ImportExtraction

StructureReader = Callable[[str], Tuple[Optional[Dict[str, Any]], Optional[str]]]
_PARALLEL_MIN_FILES = 200
_PARALLEL_MAX_WORKERS = 16

def worker_count(n_files: int) -> int:
    """Workers to use for `n_files`. 1 = run serially (no pool).

    `REVEAL_MAX_WORKERS` overrides everything (set to 1 to force the serial
    path — used by tests and for debugging); otherwise parallelize only above
    `_PARALLEL_MIN_FILES`, capped at `_PARALLEL_MAX_WORKERS` and the CPU count.
    """
    if n_files < _PARALLEL_MIN_FILES:
        return pool_worker_count(1)
    return pool_worker_count(min(os.cpu_count() or 1, _PARALLEL_MAX_WORKERS))


def extract_one_file(fp_str: str, structure_reader: Optional[StructureReader],
                      inputs: Optional[resolution.ResolutionInputs] = None):
    """Extract imports/symbols (+ optional AST structure) for a single file.

    Module-level and picklable so it runs unchanged under a
    `ProcessPoolExecutor` (fork *or* spawn). Returns
    `(fp_str, imports_or_None, symbols_or_None, structure_or_None, extraction, structure_failure_or_None,
    entry_or_None)`:
    `imports`/`symbols` are None when the file has no import extractor (mirrors
    the serial path only populating them for extractable files); `structure`
    is None when not requested or when analysis raised (`structure_failure` then
    names the error). Import extraction errors are NOT
    swallowed here — the serial path lets them propagate too. `extraction.parse_failed` is True
    when the extractor had one (i.e. the file's language IS supported) but
    tree-sitter could not parse it (`extractor.parse_failed`, BACK-982) — such
    a file's `imports`/`symbols` are an empty/partial result, not a confirmed-
    clean one, so callers (I001/I002, this adapter's own summary) must not
    treat it the same as a genuinely-clean file.

    With the cascade's project-wide *inputs* (BACK-1054) the file is read as the cascade reads it
    (PHP gets the constant index) and also indexed where it was parsed (``resolution.index_file``),
    so the main process never parses it again; ``entry`` is None without them or an extractor.
    """
    fp = Path(fp_str)
    imports = symbols = structure = structure_failure = entry = None
    extraction = None
    extractor = get_extractor(fp)
    if extractor is not None:
        if inputs is None:
            imports = extractor.extract_imports(fp)
        else:
            imports = resolution.extract_file(fp, extractor, inputs.constant_index)
        symbols = extractor.extract_symbols(fp)
        if hasattr(extractor, 'extract_exports'):
            symbols = symbols | extractor.extract_exports(fp)
        extraction = extractor.analysis
        if inputs is not None:
            entry = resolution.index_file(fp, extractor, imports, inputs.manifest_dirs)
    if structure_reader is not None:
        # Structure is a separate add-on (only requested via collect_structures=True).
        # analyze_file_outcome catches an analysis failure itself and returns it, so it
        # reaches the run's analysis_failed warning instead of reading as "this file has
        # no structure"; an exception that still escapes (a failed import, a bug) fails
        # the chunk, which _extract_files records per file (BACK-1059, BACK-1856).
        structure, structure_failure = structure_reader(fp_str)
    return fp_str, imports, symbols, structure, extraction, structure_failure, entry


def extract_chunk(job: Tuple[List[str], Optional[StructureReader], Optional[resolution.ResolutionInputs]]) -> list:
    """`extract_one_file` over one chunk of paths: the pool's unit of work."""
    paths, structure_reader, inputs = job
    return [extract_one_file(fp_str, structure_reader, inputs) for fp_str in paths]


def recording_entries(rows, entries: Optional[Dict[Path, resolution.FileEntry]]):
    """``_extract_files`` rows without their last element, the file's ``FileEntry``, which lands in
    *entries* (a file with no extractor, or lost to a dead worker, has none)."""
    for fp, *rest, entry in rows:
        if entry is not None and entries is not None:
            entries[fp] = entry
        yield (fp, *rest)


def lost_extraction(error: BaseException) -> ImportExtraction:
    """The extraction record of a file a dead pool worker lost: failed, with the
    cause, like a file its extractor could not parse (BACK-1726)."""
    return ImportExtraction(parse_failed=True, worker_lost=True, diagnostics={
        'parse': {'status': 'unavailable', 'reason': f"{type(error).__name__}: {error}"}})


def extract_files(candidates: List[Path], structure_reader: Optional[StructureReader],
                   inputs: Optional[resolution.ResolutionInputs] = None):
    """Yield ``(Path, imports_or_None, symbols_or_None, structure_or_None, extraction,
    structure_failure_or_None, entry_or_None)``
    per candidate file, in candidate order.

    Fans the independent per-file extraction out across processes when the
    repo is large enough to pay back pool startup (`worker_count`);
    otherwise runs it inline. Chunks are read in submission order, so the
    caller's assembly is identical either way. A file lost to a dead worker
    (which fails every pending chunk) is yielded with no imports and a failed
    extraction (`lost_extraction`), so it reaches ``files_failed`` and the
    run's partial-parse warning instead of failing the whole run (BACK-1726).
    """
    workers = worker_count(len(candidates))
    if workers <= 1:
        for fp in candidates:
            yield (fp, *extract_one_file(str(fp), structure_reader, inputs)[1:])
        return

    from concurrent.futures import ProcessPoolExecutor
    from ...logging_setup import worker_bootstrap

    n = len(candidates)
    # A few chunks per worker balances load without excessive IPC round-trips.
    chunksize = max(1, n // (workers * 8))
    chunks = [[str(fp) for fp in candidates[i:i + chunksize]] for i in range(0, n, chunksize)]
    with ProcessPoolExecutor(
        max_workers=workers, initializer=worker_bootstrap,
    ) as executor:
        futures = submit_each(executor, extract_chunk, [(chunk, structure_reader, inputs) for chunk in chunks])
        for chunk, future in zip(chunks, futures):
            try:
                rows = future.result()
            except Exception as e:  # boundary-ok: broad-except -- future.result() re-raises whatever the worker raised: BrokenProcessPool when it died, or any exception an extractor threw on one file of the chunk; the chunk's files are recorded as failed extractions (lost_extraction carries the cause) and reach files_failed and the partial-parse warning
                rows = [(fp_str, None, None, None, lost_extraction(e), None, None) for fp_str in chunk]
            for fp_str, *rest in rows:
                yield (Path(fp_str), *rest)
