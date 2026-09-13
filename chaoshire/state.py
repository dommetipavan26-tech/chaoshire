"""Temporary in-memory state.

This module makes the current prototype limitation explicit. A later release
will replace these objects with persistent repositories. ``UPLOADED_LOCK``
makes the single shared upload slot safe to swap while other requests read it.
"""
import threading
from typing import Any

APPEALS: list[dict[str, Any]] = []
UPLOADED: dict[str, Any] = {"df": None, "metadata": None, "audit": None}
UPLOADED_LOCK = threading.Lock()
