"""Things only a desktop can do for the local app: ask the operating system for a folder.

The app runs on your own machine, so it can open the system's folder dialog (through Tk, which ships with Python). The dialog
runs in a separate process: Tk wants to own its thread, and the app's server has many.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DIALOG = (
    "import sys, tkinter as tk\n"
    "from tkinter import filedialog\n"
    "root = tk.Tk(); root.withdraw()\n"
    "root.attributes('-topmost', True)\n"
    "print(filedialog.askdirectory(initialdir=sys.argv[1], title=sys.argv[2], mustexist=True) or '')\n"
)


class DesktopError(RuntimeError):
    """The folder dialog could not be opened (no desktop session, or Python without Tk). The message says what to do instead."""


def choose_folder(start: str | Path = ".", title: str = "Choose the folder with your products") -> str | None:
    """The folder the person picks in the system's dialog, or None if they cancel."""
    start = Path(start).expanduser()
    initial = str(start if start.is_dir() else start.parent if start.parent.is_dir() else Path.home())
    try:
        done = subprocess.run([sys.executable, "-c", DIALOG, initial, title], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise DesktopError("the folder dialog was left open too long; type the folder's path instead") from None
    if done.returncode != 0:
        why = done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "unknown error"
        raise DesktopError(f"could not open a folder dialog here ({why}); type the folder's path instead")
    return done.stdout.strip() or None
