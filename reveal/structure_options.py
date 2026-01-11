"""Configuration options for get_structure() methods.

Reduces parameter count in analyzer get_structure() methods by grouping
related options into typed configuration objects.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class StructureOptions:
    """Configuration options for structure extraction.

    Reduces R913 violations (too many arguments) by grouping related
    parameters into a single config object.

    Example:
        >>> opts = StructureOptions(head=10, extract_links=True)
        >>> analyzer.get_structure(opts)
    """

    # Filtering options
    head: Optional[int] = None
    tail: Optional[int] = None
    range: Optional[Tuple[int, int]] = None

    # Link extraction options
    extract_links: bool = False
    link_type: Optional[str] = None
    domain: Optional[str] = None
    broken: bool = False

    # Markdown-specific options
    extract_code: bool = False
    language: Optional[str] = None
    inline_code: bool = False
    extract_frontmatter: bool = False
    extract_related: bool = False
    related_depth: int = 1
    related_limit: int = 100

    # HTML-specific options
    semantic: Optional[str] = None
    metadata: bool = False
    scripts: Optional[str] = None
    styles: Optional[str] = None
    outline: bool = False

    # Additional kwargs for adapter-specific options
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_kwargs(cls, **kwargs) -> 'StructureOptions':
        """Create StructureOptions from keyword arguments.

        Allows backward compatibility with existing function signatures.
        Unknown kwargs are stored in 'extra' dict.

        Args:
            **kwargs: Keyword arguments matching StructureOptions fields

        Returns:
            StructureOptions instance

        Example:
            >>> opts = StructureOptions.from_kwargs(head=10, extract_links=True)
        """
        # Get known field names
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        known_fields.discard('extra')  # Don't treat extra as a regular field

        # Separate known and unknown kwargs
        known_kwargs = {k: v for k, v in kwargs.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in kwargs.items() if k not in known_fields}

        return cls(**known_kwargs, extra=extra_kwargs)

    def to_dict(self) -> dict:
        """Convert options back to dictionary format.

        Useful for backward compatibility and serialization.

        Returns:
            Dictionary of non-None options
        """
        result = {}
        for key, value in self.__dict__.items():
            if key == 'extra':
                result.update(value)  # Merge extra kwargs
            elif value is not None and value is not False:
                result[key] = value
        return result
