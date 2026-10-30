"""The retired architecture spelling delegates to the canonical project map."""

from typing import Any, Dict

from .base import register_adapter, register_renderer
from .overview import OverviewAdapter
from ..rendering.adapters.architecture import ArchitectureRenderer


@register_adapter('architecture')
@register_renderer(ArchitectureRenderer)
class ArchitectureAdapter(OverviewAdapter):
    """D5 note-stage alias; the central retirement table supplies the note."""

    # Factory binding deliberately requires a class-local declaration.
    BOUND_QUERY_CALL = True

    @staticmethod
    def get_help() -> Dict[str, Any]:
        help_data = dict(OverviewAdapter.get_help())
        help_data.update(
            name='architecture',
            syntax='architecture://<path>[?top=5&no_imports=true|against=REF]',
            examples=[{**example, 'uri': example['uri'].replace('overview://', 'architecture://', 1)}
                      for example in help_data['examples']],
            notes=['Retired spelling of overview:// (the same answer); use overview for project maps '
                   'and comparisons.', *help_data['notes']],
        )
        return help_data

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        schema = dict(OverviewAdapter.get_schema())
        schema.update(
            adapter='architecture',
            uri_syntax='architecture://<path>?top=5&no_imports=true|against=REF',
            example_queries=[{**example, 'uri': example['uri'].replace('overview://', 'architecture://', 1)}
                             for example in schema['example_queries']],
            notes=['Retired spelling of overview:// (the same canonical overview or overview_diff answer).',
                   *schema['notes']],
        )
        return schema
