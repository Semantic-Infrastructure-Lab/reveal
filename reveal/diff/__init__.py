"""Diff module for comparing reveal structures."""

from .structure_diff import (
    compute_structure_diff,
    compute_element_diff,
)
from .architecture_diff import (
    run_architecture_diff,
    diff_snapshots,
)

__all__ = [
    'compute_structure_diff',
    'compute_element_diff',
    'run_architecture_diff',
    'diff_snapshots',
]
