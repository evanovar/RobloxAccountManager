import hashlib
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from classes import encryption
from classes.encryption import HardwareEncryption

GOOD = {
    "Win32_ComputerSystemProduct": [SimpleNamespace(UUID="UUID-1")],
    "Win32_Processor": [SimpleNamespace(ProcessorId="CPU-2")],
    "Win32_BaseBoard": [SimpleNamespace(SerialNumber="BOARD-3")],
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def fake_com(rows, connect_error=None, init_error=None):
    pythoncom = MagicMock()
    if init_error is not None:
        pythoncom.CoInitialize.side_effect = init_error
    service = MagicMock()
    service.ExecQuery.side_effect = lambda query: rows[query.split(" FROM ")[1]]
    locator = MagicMock()
    if connect_error is not None:
        locator.ConnectServer.side_effect = connect_error
    else:
        locator.ConnectServer.return_value = service
    client = MagicMock()
    client.Dispatch.return_value = locator
    package = MagicMock(client=client)
    modules = {"pythoncom": pythoncom, "win32com": package, "win32com.client": client}
    return pythoncom, modules


class ReadWmiIdentifiersTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(encryption.platform, "system", return_value="Windows"))

    def read(self, rows, **errors):
        pythoncom, modules = fake_com(rows, **errors)
        with patch.dict(sys.modules, modules):
            return encryption._read_wmi_identifiers(), pythoncom

    def test_one_value_per_class_is_returned_in_order(self):
        values, pythoncom = self.read(GOOD)
        self.assertEqual(values, ["UUID-1", "CPU-2", "BOARD-3"])
        pythoncom.CoInitialize.assert_called_once()
        pythoncom.CoUninitialize.assert_called_once()

    def test_surrounding_whitespace_is_stripped_like_the_powershell_output(self):
        rows = {**GOOD, "Win32_BaseBoard": [SimpleNamespace(SerialNumber="  BOARD-3 \r\n")]}
        self.assertEqual(self.read(rows)[0][2], "BOARD-3")

    def test_anything_that_could_differ_from_powershell_returns_none(self):
        cases = {
            "no rows": {**GOOD, "Win32_Processor": []},
            "two rows": {**GOOD, "Win32_Processor": [SimpleNamespace(ProcessorId="A"), SimpleNamespace(ProcessorId="B")]},
            "empty value": {**GOOD, "Win32_BaseBoard": [SimpleNamespace(SerialNumber="   ")]},
            "missing value": {**GOOD, "Win32_BaseBoard": [SimpleNamespace(SerialNumber=None)]},
            "not text": {**GOOD, "Win32_BaseBoard": [SimpleNamespace(SerialNumber=5)]},
        }
        for name, rows in cases.items():
            with self.subTest(case=name):
                values, pythoncom = self.read(rows)
                self.assertIsNone(values)
                pythoncom.CoUninitialize.assert_called_once()

    def test_wmi_errors_return_none_and_still_uninitialize(self):
        values, pythoncom = self.read(GOOD, connect_error=OSError("no WMI"))
        self.assertIsNone(values)
        pythoncom.CoUninitialize.assert_called_once()

    def test_a_com_apartment_conflict_returns_none_without_uninitializing(self):
        values, pythoncom = self.read(GOOD, init_error=OSError("changed mode"))
        self.assertIsNone(values)
        pythoncom.CoUninitialize.assert_not_called()

    def test_missing_pywin32_returns_none(self):
        with patch.dict(sys.modules, {"pythoncom": None}):
            self.assertIsNone(encryption._read_wmi_identifiers())

    def test_other_platforms_return_none(self):
        with patch.object(encryption.platform, "system", return_value="Linux"):
            self.assertIsNone(encryption._read_wmi_identifiers())


class MachineIdUsesWmiTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(encryption._MACHINE_ID_CACHE, {}, clear=True))
        self.enterContext(patch.object(encryption.platform, "system", return_value="Windows"))
        self.reader = HardwareEncryption.__new__(HardwareEncryption)

    def test_wmi_values_give_the_same_id_as_the_powershell_values(self):
        with patch.object(encryption, "_read_wmi_identifiers", return_value=["UUID-1", "CPU-2", "BOARD-3"]), \
                patch.object(encryption.subprocess, "check_output") as powershell:
            fast = self.reader._get_machine_id()
        powershell.assert_not_called()

        encryption._MACHINE_ID_CACHE.clear()
        outputs = {0: b"UUID-1\r\n", 1: b"CPU-2\r\n", 2: b"BOARD-3\r\n"}
        commands = iter(range(3))
        with patch.object(encryption, "_read_wmi_identifiers", return_value=None), \
                patch.object(encryption.subprocess, "check_output", side_effect=lambda *a, **k: outputs[next(commands)]):
            slow = self.reader._get_machine_id()
        self.assertEqual(fast, slow)
        self.assertEqual(fast, digest("UUID-1-CPU-2-BOARD-3"))

    def test_falls_back_to_powershell_when_wmi_is_not_usable(self):
        with patch.object(encryption, "_read_wmi_identifiers", return_value=None), \
                patch.object(encryption.subprocess, "check_output", return_value=b"X\r\n") as powershell:
            self.assertEqual(self.reader._get_machine_id(), digest("X-X-X"))
        self.assertEqual(powershell.call_count, 3)

    def test_result_is_cached(self):
        with patch.object(encryption, "_read_wmi_identifiers", return_value=["a", "b", "c"]) as read:
            first = self.reader._get_machine_id()
            second = self.reader._get_machine_id()
        self.assertEqual(first, second)
        read.assert_called_once()


@unittest.skipUnless(sys.platform == "win32", "WMI is Windows only")
class RealMachineTests(unittest.TestCase):
    def test_wmi_matches_the_powershell_lookup_on_this_machine(self):
        fast = encryption._read_wmi_identifiers()
        if fast is None:
            self.skipTest("this machine reports values the fast path does not handle")
        queries = [
            "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
            "(Get-CimInstance Win32_Processor).ProcessorId",
            "(Get-CimInstance Win32_BaseBoard).SerialNumber",
        ]
        slow = [
            subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", query],
                creationflags=0x08000000,
                timeout=30,
            ).decode(errors="ignore").strip()
            for query in queries
        ]
        self.assertEqual(fast, slow)


if __name__ == "__main__":
    unittest.main()
