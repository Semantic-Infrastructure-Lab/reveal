"""Base analyzer interface."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List


class BaseAnalyzer(ABC):
    """Base class for file type analyzers."""

    def __init__(self, lines: List[str]):
        """
        Initialize analyzer with file lines.

        Args:
            lines: List of file lines
        """
        self.lines = lines

    @abstractmethod
    def analyze_structure(self) -> Dict[str, Any]:
        """
        Analyze file structure for Level 1.

        Returns:
            Dictionary with structural information
        """
        pass

    @abstractmethod
    def generate_preview(self) -> List[tuple[int, str]]:
        """
        Generate preview for Level 2.

        Returns:
            List of (line_number, content) tuples
        """
        pass
