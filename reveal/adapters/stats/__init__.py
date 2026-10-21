"""metrics:// (and its retired spelling stats://) -- modularized for maintainability."""

from .adapter import MetricsAdapter, StatsAdapter
from .renderer import StatsRenderer

__all__ = ['MetricsAdapter', 'StatsAdapter', 'StatsRenderer']
