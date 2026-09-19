"""Bounded in-memory demo state.

Two prototype limitations are made explicit here rather than hidden:

* ``UPLOADED`` is a single shared slot holding the most recent **published**
  audit. ``UPLOADED_LOCK`` makes it safe to swap while other requests read it.
  Only uploads authenticated with ``CHAOSHIRE_API_KEY`` are published; see
  :mod:`chaoshire.platform`.
* ``APPEALS`` is a **bounded** FIFO queue. The public demo accepts appeals from
  anyone, so an unbounded list would be a trivial memory-exhaustion vector on a
  512 MB instance: 5,000-character messages appended forever. Capacity comes
  from ``CHAOSHIRE_MAX_APPEALS``; once it is reached the oldest appeal is
  evicted and counted.

Both structures are process-local and are lost on restart or redeploy. Neither
is a system of record.
"""

import itertools
import os
import threading
from collections import deque
from collections.abc import Iterator
from typing import Any

DEFAULT_APPEALS_CAPACITY = 200

UPLOADED: dict[str, Any] = {"df": None, "metadata": None, "audit": None}
UPLOADED_LOCK = threading.Lock()


def appeals_capacity() -> int:
    """Configured capacity of the in-memory appeal queue (minimum 1)."""
    raw = (os.getenv("CHAOSHIRE_MAX_APPEALS") or "").strip()
    if not raw:
        return DEFAULT_APPEALS_CAPACITY
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_APPEALS_CAPACITY


class AppealQueue:
    """Thread-safe, capacity-bounded, newest-first appeal queue.

    Deliberately a mutable object rather than a module-level ``deque`` name so
    the capacity can be reconfigured without rebinding the global that
    ``backend.py`` re-exports for backward compatibility.
    """

    def __init__(self, capacity: int) -> None:
        self._lock = threading.Lock()
        self._items: deque[dict[str, Any]] = deque(maxlen=max(1, capacity))
        self._sequence = itertools.count(1)
        self._evicted = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        with self._lock:
            return iter(list(self._items))

    def __reversed__(self) -> Iterator[dict[str, Any]]:
        with self._lock:
            return iter(list(reversed(self._items)))

    @property
    def capacity(self) -> int:
        with self._lock:
            return int(self._items.maxlen or 0)

    def set_capacity(self, capacity: int) -> None:
        """Resize the queue, evicting oldest-first if it must shrink."""
        with self._lock:
            resized = deque(self._items, maxlen=max(1, capacity))
            self._evicted += len(self._items) - len(resized)
            self._items = resized

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._evicted = 0

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        """Assign a monotonic id, append, and return the stored record.

        Ids come from a process-wide sequence rather than ``len(...) + 1`` so
        they stay unique after evictions.
        """
        with self._lock:
            stored = {**record, "id": next(self._sequence)}
            if self._items.maxlen is not None and len(self._items) == self._items.maxlen:
                self._evicted += 1
            self._items.append(stored)
            return stored

    def snapshot(self) -> dict[str, Any]:
        """Newest-first appeals plus the queue's capacity, for honest reporting."""
        with self._lock:
            items = list(reversed(self._items))
            capacity = int(self._items.maxlen or 0)
            evicted = self._evicted
        note = (
            "Demonstration queue held in process memory, newest first. It is capped at "
            f"{capacity} entries and the oldest appeal is evicted beyond that; it is not "
            "a case-management system and is cleared on every restart or redeploy."
        )
        if evicted:
            note += f" {evicted} older appeal(s) have already been evicted."
        return {
            "appeals": items,
            "count": len(items),
            "capacity": capacity,
            "evicted": evicted,
            "bounded": True,
            "note": note,
        }


APPEALS = AppealQueue(appeals_capacity())


def reset_appeals() -> None:
    """Empty the queue and its eviction counter (used by test isolation)."""
    APPEALS.clear()


def append_appeal(record: dict[str, Any]) -> dict[str, Any]:
    return APPEALS.append(record)


def appeals_snapshot() -> dict[str, Any]:
    return APPEALS.snapshot()
