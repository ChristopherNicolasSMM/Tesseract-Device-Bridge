"""Serial maintenance toolkit, usable without Flask, storage or Bridge runtime."""
from .service import SerialError, SerialMonitor

__all__ = ['SerialError', 'SerialMonitor']
