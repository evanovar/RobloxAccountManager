"""
Atomic JSON file writes.
"""

from __future__ import annotations

import json
import os
import tempfile


def write_json_atomic(path: str, data, prefix: str = ".atomic.", fsync: bool = False) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    try:
        try:
            handle = os.fdopen(descriptor, "w", encoding="utf-8")
        except BaseException:
            os.close(descriptor)
            raise
        with handle:
            json.dump(data, handle, indent=2)
            if fsync:
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def quarantine_corrupt(path: str) -> None:
    target = path + ".corrupt"
    try:
        os.replace(path, target)
    except OSError:
        return
    print(
        f"[WARNING] {os.path.basename(path)} could not be read. "
        f"It was moved to {os.path.basename(target)}."
    )
