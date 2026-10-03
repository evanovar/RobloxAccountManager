"""Time the parts of startup and saving that depend on encryption.

Run from the project root:

    uv run --no-sync python scripts/benchmark_encryption.py
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from classes import account_manager as am  # noqa: E402
from classes import encryption  # noqa: E402

ACCOUNT_COUNTS = (10, 100, 1000)
RUNS = 5


def timed(func, runs=RUNS):
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        func()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples), min(samples)


def report(label, func, runs=RUNS):
    median, best = timed(func, runs)
    print(f"{label:<42} median {median * 1000:9.1f} ms   best {best * 1000:9.1f} ms")


def fresh_machine_id():
    encryption._MACHINE_ID_CACHE.clear()
    encryption.HardwareEncryption()


def make_accounts(count):
    return {
        f"user{i}": {
            "username": f"user{i}",
            "cookie": "_|WARNING:-DO-NOT-SHARE-THIS|_" + "x" * 800,
            "user_id": i,
            "note": "",
            "cookie_valid": True,
        }
        for i in range(count)
    }


def bench_save_and_load(method, count):
    with tempfile.TemporaryDirectory() as folder:
        with mock.patch.object(am, "get_data_dir", return_value=folder), \
                mock.patch.object(encryption.HardwareEncryption, "_get_machine_id", return_value="bench"):
            manager = am.RobloxAccountManager()
            if method != "none":
                manager.switch_encryption_method(method, password="bench-password")
            manager.accounts = make_accounts(count)
            report(f"save, {method}, {count} accounts", manager.save_accounts)
            report(f"load, {method}, {count} accounts", manager.load_accounts)


def main():
    print("Hardware key setup (spawns PowerShell, cache cleared each run)")
    report("HardwareEncryption()", fresh_machine_id, runs=3)
    print("\nPassword key derivation")
    report("PasswordEncryption(PBKDF2, 100k rounds)", lambda: encryption.PasswordEncryption("pw"))
    print("\nSaving and loading accounts")
    for method in ("none", "hardware", "password"):
        for count in ACCOUNT_COUNTS:
            bench_save_and_load(method, count)


if __name__ == "__main__":
    main()
