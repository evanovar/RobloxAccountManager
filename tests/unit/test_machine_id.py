import hashlib
import subprocess
import unittest
from unittest.mock import patch

from classes import encryption
from classes.encryption import HardwareEncryption


COMMANDS = (
    "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
    "(Get-CimInstance Win32_Processor).ProcessorId",
    "(Get-CimInstance Win32_BaseBoard).SerialNumber",
)
VALUES = dict(zip(COMMANDS, (b"UUID-1\r\n", b"CPU-2\r\n", b"BOARD-3\r\n")))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class StableMachineIdTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(encryption._MACHINE_ID_CACHE, {}, clear=True))
        self.enterContext(patch.object(encryption.platform, "system", return_value="Windows"))
        self.enterContext(patch.object(encryption.platform, "node", return_value="test-host"))
        self.enterContext(patch.object(encryption.platform, "machine", return_value="AMD64"))
        # Avoid real key derivation and hardware queries during construction.
        self.reader = HardwareEncryption.__new__(HardwareEncryption)

    def test_identifiers_are_joined_in_a_fixed_order(self):
        with patch.object(encryption.subprocess, "check_output", side_effect=lambda args, **kw: VALUES[args[-1]]) as run:
            result = self.reader._get_machine_id()
        self.assertEqual(result, digest("UUID-1-CPU-2-BOARD-3"))
        self.assertEqual({call.args[0][-1] for call in run.call_args_list}, set(COMMANDS))
        self.assertEqual(run.call_count, 3)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["timeout"], 10)
            self.assertEqual(call.kwargs["creationflags"], 0x08000000)

    def test_failures_preserve_only_identifiers_before_the_failed_query(self):
        for failed_index in range(3):
            for error in (
                OSError("PowerShell missing"),
                subprocess.TimeoutExpired("powershell", 10),
                subprocess.CalledProcessError(1, "powershell"),
            ):
                with self.subTest(query=failed_index, error=type(error).__name__):
                    encryption._MACHINE_ID_CACHE.clear()

                    def query(args, **kwargs):
                        if args[-1] == COMMANDS[failed_index]:
                            raise error
                        return VALUES[args[-1]]

                    prefix = ["UUID-1", "CPU-2", "BOARD-3"][:failed_index]
                    expected = digest("-".join(prefix + ["test-host", "AMD64"]))
                    with patch.object(encryption.subprocess, "check_output", side_effect=query):
                        self.assertEqual(self.reader._get_machine_id(), expected)

    def test_multiline_cpu_identifiers_keep_their_original_separator(self):
        values = {**VALUES, COMMANDS[1]: b"CPU-1\r\nCPU-2\r\n"}
        with patch.object(encryption.subprocess, "check_output", side_effect=lambda args, **kw: values[args[-1]]):
            self.assertEqual(self.reader._get_machine_id(), digest("UUID-1-CPU-1\r\nCPU-2-BOARD-3"))

    def test_empty_identifier_is_kept_in_the_key_material(self):
        values = {**VALUES, COMMANDS[1]: b"\r\n"}
        with patch.object(encryption.subprocess, "check_output", side_effect=lambda args, **kw: values[args[-1]]):
            self.assertEqual(self.reader._get_machine_id(), digest("UUID-1--BOARD-3"))

    def test_invalid_output_bytes_are_ignored_without_changing_other_values(self):
        values = {**VALUES, COMMANDS[0]: b" UUID-1\xff\r\n"}
        with patch.object(encryption.subprocess, "check_output", side_effect=lambda args, **kw: values[args[-1]]):
            self.assertEqual(self.reader._get_machine_id(), digest("UUID-1-CPU-2-BOARD-3"))

    def test_result_is_cached(self):
        with patch.object(encryption.subprocess, "check_output", side_effect=lambda args, **kw: VALUES[args[-1]]) as run:
            first = self.reader._get_machine_id()
            second = HardwareEncryption.__new__(HardwareEncryption)._get_machine_id()
        self.assertEqual(first, second)
        self.assertEqual(run.call_count, 3)

    def test_cached_id_does_not_query_hardware(self):
        encryption._MACHINE_ID_CACHE["stable"] = "already-cached"
        with patch.object(encryption.subprocess, "check_output") as run:
            self.assertEqual(self.reader._get_machine_id(), "already-cached")
        run.assert_not_called()

    def test_non_windows_id_keeps_hostname_and_user_id(self):
        with patch.object(encryption.platform, "system", return_value="Linux"), patch.object(
            encryption.os, "getuid", return_value=42, create=True,
        ), patch.object(encryption.subprocess, "check_output") as run:
            self.assertEqual(self.reader._get_machine_id(), digest("test-host-42"))
        run.assert_not_called()
