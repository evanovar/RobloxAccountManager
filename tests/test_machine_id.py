import hashlib
import os
import platform
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from classes import encryption
from classes.encryption import HardwareEncryption

VALUES = {
    "Win32_ComputerSystemProduct": b"UUID-1\r\n",
    "Win32_Processor": b"CPU-2\r\n",
    "Win32_BaseBoard": b"BOARD-3\r\n",
}


def fake_check_output(args, **kwargs):
    command = args[-1]
    for key, value in VALUES.items():
        if key in command:
            return value
    raise AssertionError(f"unexpected command: {command}")


def stable_id():
    encryption._MACHINE_ID_CACHE.clear()
    with mock.patch.object(HardwareEncryption, "__init__", lambda self: None):
        return HardwareEncryption()._get_machine_id()


class StableMachineIdTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(encryption._MACHINE_ID_CACHE.clear)
        patch = mock.patch.object(encryption.platform, "system", return_value="Windows")
        patch.start()
        self.addCleanup(patch.stop)

    def test_identifiers_are_joined_in_a_fixed_order(self):
        with mock.patch.object(encryption.subprocess, "check_output", side_effect=fake_check_output):
            self.assertEqual(stable_id(), hashlib.sha256(b"UUID-1-CPU-2-BOARD-3").hexdigest())

    def test_failed_lookup_keeps_earlier_identifiers_and_appends_fallback(self):
        def flaky(args, **kwargs):
            if "Win32_Processor" in args[-1]:
                raise OSError("powershell failed")
            return fake_check_output(args, **kwargs)

        expected = f"UUID-1-{platform.node()}-{platform.machine()}".encode()
        with mock.patch.object(encryption.subprocess, "check_output", side_effect=flaky):
            self.assertEqual(stable_id(), hashlib.sha256(expected).hexdigest())

    def test_first_lookup_failing_uses_only_the_fallback(self):
        with mock.patch.object(encryption.subprocess, "check_output", side_effect=OSError("no powershell")):
            expected = f"{platform.node()}-{platform.machine()}".encode()
            self.assertEqual(stable_id(), hashlib.sha256(expected).hexdigest())

    def test_result_is_cached(self):
        with mock.patch.object(encryption.subprocess, "check_output", side_effect=fake_check_output) as run:
            first = stable_id()
            with mock.patch.object(HardwareEncryption, "__init__", lambda self: None):
                second = HardwareEncryption()._get_machine_id()
        self.assertEqual(first, second)
        self.assertEqual(run.call_count, 3)


if __name__ == "__main__":
    unittest.main()
