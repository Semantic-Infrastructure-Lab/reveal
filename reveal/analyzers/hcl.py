"""HCL (HashiCorp Configuration Language) analyzer using tree-sitter."""
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.tf', '.tfvars', '.hcl', name='HCL', icon='🏗️')
class HCLAnalyzer(TreeSitterAnalyzer):
    """HCL/Terraform language analyzer.

    Supports Terraform (.tf), Terraform variables (.tfvars),
    and generic HCL (.hcl) configuration files.
    """
    language = 'hcl'
