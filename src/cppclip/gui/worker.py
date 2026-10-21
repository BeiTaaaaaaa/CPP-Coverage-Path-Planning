"""Run planning off the GUI thread.

A plan on a 20 ha field takes a few hundred milliseconds, and the heading search
plus a full re-plan of the incremental demo can take seconds.  Blocking the
event loop for that long freezes the window, which reads as a crash -- so every
plan goes through a worker.

The design is the standard Qt one: a :class:`QRunnable` carrying a callable,
with a small signal-owning object because ``QRunnable`` itself is not a
``QObject``.  Results cross the thread boundary as plain Python objects, and the
worker never touches a widget.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

__all__ = ["TaskSignals", "Task", "run_async"]


class TaskSignals(QObject):
    """Signals for one :class:`Task`.  Separate because QRunnable is not a QObject."""

    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)


class Task(QRunnable):
    """Run ``fn(*args, **kwargs)`` on the pool and emit whatever it returns."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = TaskSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102 - QRunnable interface
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception:  # noqa: BLE001 - a worker must never kill the app
            self.signals.failed.emit(traceback.format_exc(limit=4))
            return
        self.signals.finished.emit(result)


#: One pool for the whole application.  A single thread is enough -- plans are
#: serialised anyway, and running two at once would make the timings the GUI
#: reports meaningless.
_POOL: QThreadPool | None = None


def pool() -> QThreadPool:
    global _POOL
    if _POOL is None:
        _POOL = QThreadPool()
        _POOL.setMaxThreadCount(1)
    return _POOL


def run_async(
    fn: Callable[..., Any],
    on_done: Callable[[Any], None],
    on_error: Callable[[str], None],
    *args: Any,
    **kwargs: Any,
) -> Task:
    """Schedule *fn* and wire its outcome to the two callbacks."""
    task = Task(fn, *args, **kwargs)
    task.signals.finished.connect(on_done)
    task.signals.failed.connect(on_error)
    pool().start(task)
    return task
