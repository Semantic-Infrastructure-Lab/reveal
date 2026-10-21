"""metrics:// -- the module the lazy scheme registry imports for the metrics scheme (BACK-2069).

The adapter is owned by the stats package (adapters/stats/), which registers metrics:// and
its retired spelling stats:// together.
"""

from .stats import MetricsAdapter

__all__ = ['MetricsAdapter']
