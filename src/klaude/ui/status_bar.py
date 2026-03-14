"""Persistent status bar at the bottom of the terminal.

Uses ANSI scroll regions to reserve the last terminal line for status.
All normal output (print, Rich, streaming, readline) stays within the
scroll region (lines 1 to rows-1), while the status bar persists on
the last line (row `rows`).

This is the same technique used by tmux, screen, and Claude Code.
"""

import atexit
import os
import signal
import sys

# Singleton reference for atexit cleanup
_active_bar: "StatusBar | None" = None


def _cleanup() -> None:
    """atexit handler — restore terminal if we crash."""
    if _active_bar is not None:
        _active_bar.stop()


atexit.register(_cleanup)


class StatusBar:
    """Persistent status line at the bottom of the terminal."""

    def __init__(self) -> None:
        self._active = False
        self._text = ""
        self._prev_sigwinch: object = None

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self) -> None:
        """Reserve the bottom line by setting a scroll region."""
        global _active_bar
        if not sys.stdout.isatty():
            return
        self._active = True
        _active_bar = self
        self._setup_scroll_region()
        # Re-setup on terminal resize
        if hasattr(signal, "SIGWINCH"):
            self._prev_sigwinch = signal.getsignal(signal.SIGWINCH)
            signal.signal(signal.SIGWINCH, self._on_resize)

    def _setup_scroll_region(self) -> None:
        """Set scroll region to [1, rows-1], reserve row `rows` for status."""
        try:
            rows = os.get_terminal_size().lines
        except OSError:
            return
        if rows < 3:
            return
        # Push existing content up by 1 line to make room
        sys.stdout.write("\n")
        # Set scroll region: lines 1 through rows-1
        sys.stdout.write(f"\033[1;{rows - 1}r")
        # Move cursor to bottom of scroll region
        sys.stdout.write(f"\033[{rows - 1};1H")
        sys.stdout.flush()
        self._redraw()

    def _redraw(self) -> None:
        """Redraw the status bar on the last terminal line."""
        if not self._active:
            return
        try:
            size = os.get_terminal_size()
            rows, cols = size.lines, size.columns
        except OSError:
            return
        # Truncate and pad to fill the line
        display = self._text[:cols].ljust(cols)
        # Save cursor -> last row -> clear -> dim text -> restore cursor
        sys.stdout.write(
            f"\0337"            # save cursor position
            f"\033[{rows};1H"   # move to last row
            f"\033[2K"          # clear the line
            f"\033[2m"          # dim
            f"{display}"
            f"\033[0m"          # reset attributes
            f"\0338"            # restore cursor position
        )
        sys.stdout.flush()

    def update(self, text: str) -> None:
        """Update the status bar content."""
        self._text = text
        if self._active:
            self._redraw()

    def _on_resize(self, signum: int, frame: object) -> None:
        """Handle SIGWINCH (terminal resize)."""
        if self._active:
            self._setup_scroll_region()
        # Chain to previous handler
        prev = self._prev_sigwinch
        if prev and callable(prev) and prev not in (signal.SIG_DFL, signal.SIG_IGN):
            prev(signum, frame)

    def stop(self) -> None:
        """Remove the status bar and restore the terminal."""
        global _active_bar
        if not self._active:
            return
        self._active = False
        _active_bar = None
        try:
            rows = os.get_terminal_size().lines
        except OSError:
            return
        # Clear status line and restore full scroll region
        sys.stdout.write(
            f"\033[{rows};1H"   # move to last row
            f"\033[2K"          # clear it
            f"\033[1;{rows}r"   # restore full scroll region
            f"\033[{rows};1H"   # cursor at bottom
        )
        sys.stdout.flush()
        # Restore previous SIGWINCH handler
        if hasattr(signal, "SIGWINCH") and self._prev_sigwinch is not None:
            signal.signal(signal.SIGWINCH, self._prev_sigwinch)
            self._prev_sigwinch = None
