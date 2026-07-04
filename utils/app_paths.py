"""
Shared filesystem paths for source runs and PyInstaller builds.
"""

from __future__ import annotations

import os
import sys


def get_project_root() -> str:
    """Return the project root in source runs or the executable folder in frozen builds."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_app_dir() -> str:
    return get_project_root()


def get_data_dir() -> str:
    return os.path.join(get_project_root(), "AccountManagerData")
