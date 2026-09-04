"""Document inspector and parser provider boundaries."""

from src.server.documents.providers.base import (
    DocumentInspector,
    DocumentParser,
    InspectorDescriptor,
    IsolatedProcessRunner,
)
from src.server.documents.providers.pdf_inspector import PdfInspectorDetector
from src.server.documents.providers.registry import DocumentProviderRegistry

__all__ = [
    "DocumentInspector",
    "DocumentParser",
    "DocumentProviderRegistry",
    "InspectorDescriptor",
    "IsolatedProcessRunner",
    "PdfInspectorDetector",
]
