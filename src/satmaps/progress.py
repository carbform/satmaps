"""Terminal progress and status reporting for decimation, sensor reads, and rendering."""
from __future__ import annotations

import sys
import threading
from typing import TextIO

_current_progress: Progress | None = None
_lock = threading.Lock()


def get_progress() -> Progress | None:
    """Return the currently active progress reporter, if any."""
    return _current_progress


class Progress:
    """Terminal progress reporter that writes status updates cleanly to stderr without corrupting stdout."""

    def __init__(self, stream: TextIO | None = None, quiet: bool = False, verbose: bool = False):
        self.stream = stream if stream is not None else sys.stderr
        self.quiet = quiet
        self.verbose = verbose
        self.is_tty = hasattr(self.stream, "isatty") and self.stream.isatty()
        self._last_len = 0
        self._active = False

    def __enter__(self) -> Progress:
        global _current_progress
        with _lock:
            _current_progress = self
        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        global _current_progress
        if self._active and self.is_tty and self._last_len > 0 and not getattr(self.stream, "closed", False):
            self.stream.write(f"\r{' ' * self._last_len}\r")
            self.stream.flush()
        with _lock:
            if _current_progress is self:
                _current_progress = None
        self._active = False

    def update(self, msg: str) -> None:
        """Update the active status line."""
        if self.quiet or getattr(self.stream, "closed", False):
            return
        if self.is_tty:
            formatted = f"\r[satmaps] {msg}"
            if len(formatted) < self._last_len:
                formatted += " " * (self._last_len - len(formatted))
            self._last_len = len(formatted)
            self.stream.write(formatted)
            self.stream.flush()
        elif self.verbose:
            self.stream.write(f"[satmaps] {msg}\n")
            self.stream.flush()

    def ticker(self, step: int, total: int, label: str = "") -> None:
        """Update a progress bar or step counter."""
        if self.quiet or getattr(self.stream, "closed", False):
            return
        total = max(1, total)
        pct = min(100, int(100 * step / total))
        bar_len = 16
        filled = int(bar_len * step / total)
        bar = "=" * filled + (">" if filled < bar_len else "") + " " * (bar_len - filled - (1 if filled < bar_len else 0))
        msg = f"{label} [{bar}] {pct:3d}%" if label else f"[{bar}] {pct:3d}%"
        self.update(msg)

    def done(self, msg: str = "") -> None:
        """Complete the current progress section."""
        if self.quiet or getattr(self.stream, "closed", False):
            return
        if self.is_tty:
            if msg:
                formatted = f"\r[satmaps] {msg}"
                if len(formatted) < self._last_len:
                    formatted += " " * (self._last_len - len(formatted))
                self.stream.write(formatted + "\n")
            else:
                self.stream.write(f"\r{' ' * self._last_len}\r")
            self.stream.flush()
            self._last_len = 0
        elif self.verbose and msg:
            self.stream.write(f"[satmaps] {msg}\n")
            self.stream.flush()
