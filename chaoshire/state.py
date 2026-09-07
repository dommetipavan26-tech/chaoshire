"""Temporary in-memory state.

This module makes the current prototype limitation explicit. A later release
will replace these objects with persistent repositories.
"""
from typing import Any

APPEALS: list[dict[str, Any]] = []
UPLOADED: dict[str, Any] = {"df": None, "metadata": None}
