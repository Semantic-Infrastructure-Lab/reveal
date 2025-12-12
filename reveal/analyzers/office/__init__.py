"""Office document analyzers for reveal.

Supports both OpenXML (Microsoft Office) and ODF (LibreOffice/OpenOffice) formats.
These are all ZIP archives containing XML files - we use pure stdlib (zipfile + xml.etree).

OpenXML: .docx, .xlsx, .pptx
ODF: .odt, .ods, .odp
"""

from .openxml import DocxAnalyzer, XlsxAnalyzer, PptxAnalyzer
from .odf import OdtAnalyzer, OdsAnalyzer, OdpAnalyzer

__all__ = [
    'DocxAnalyzer',
    'XlsxAnalyzer',
    'PptxAnalyzer',
    'OdtAnalyzer',
    'OdsAnalyzer',
    'OdpAnalyzer',
]
