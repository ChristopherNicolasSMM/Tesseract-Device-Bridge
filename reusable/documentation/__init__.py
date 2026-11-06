"""Read-only documentation catalog, safe Markdown viewer and optional Flask adapter.

No storage, runtime, device, framework or network imports at package load time.
"""
from .catalog import DocumentError, DocumentLibrary

__all__ = ['DocumentError', 'DocumentLibrary']
