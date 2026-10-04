import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

import win32api
import win32con
import win32security

from features import account_actions as actions
from features import handle64_trust as trust

SIGNED_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\EdgeUpdate\MicrosoftEdgeUpdate.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\EdgeUpdate\MicrosoftEdgeUpdate.exe",
)
SIGNED_EXE = next((path for path in SIGNED_CANDIDATES if os.path.isfile(path)), None)
CMD_EXE = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
REAL_CREATE_PROTECTED = trust.create_protected_directory
REAL_RUN = subprocess.run


def current_user_sid():
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])


def force_remove(path):
    # Protected folders only allow administrators, so give ourselves access first.
    if not os.path.exists(path):
        return
    dacl = win32security.ACL()
    dacl.AddAccessAllowedAce(
        win32security.ACL_REVISION, 0x1F01FF, win32security.ConvertStringSidToSid(current_user_sid())
    )
    try:
        win32security.SetNamedSecurityInfo(
            path, win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION | win32security.UNPROTECTED_DACL_SECURITY_INFORMATION,
            None, None, dacl, None,
        )
    except Exception:
        pass
    shutil.rmtree(path, ignore_errors=True)


class Workspace(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.me = current_user_sid()
        trust.release_trusted_copies()
        self.addCleanup(self.cleanup_copies)
        self.created = []
        self.addCleanup(lambda: [force_remove(path) for path in self.created])

    def cleanup_copies(self):
        trust.release_trusted_copies()

    def make_protected(self, **kwargs):
        path = trust.create_protected_directory(self.folder, **kwargs)
        self.created.append(path)
        return path

    def fake_source(self, data=b"MZ-test-handle64", name="handle64.exe"):
        path = os.path.join(self.folder, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def trusted(self, source, **kwargs):
        return trust.trusted_executable(source, root=self.folder, extra_sids=(self.me,), **kwargs)

    def signed_source(self):
        path = os.path.join(self.folder, "source", "handle64.exe")
        os.makedirs(os.path.dirname(path))
        shutil.copy(SIGNED_EXE, path)
        return path


@unittest.skipUnless(SIGNED_EXE, "needs a Microsoft binary with an embedded signature")
class NativeSignatureTests(Workspace):
    def check(self, path):
        with trust.open_locked(path) as handle:
            return trust.signer_organization(handle), trust.is_trusted_signature(handle)

    def test_a_microsoft_binary_with_an_embedded_signature_is_trusted(self):
        self.assertEqual(self.check(SIGNED_EXE), ("Microsoft Corporation", True))

    def test_a_catalog_signed_windows_file_has_no_embedded_signature_and_is_refused(self):
        self.assertEqual(self.check(CMD_EXE), (None, False))

    def test_another_publisher_is_refused_even_though_it_is_signed(self):
        organization, trusted = self.check(os.path.join(sys.base_prefix, "python.exe"))
        self.assertEqual(organization, "Python Software Foundation")
        self.assertFalse(trusted)

    def test_an_unsigned_file_is_refused(self):
        self.assertEqual(self.check(self.fake_source(b"MZ" + b"\x00" * 300)), (None, False))

    def test_a_tampered_copy_of_a_signed_file_is_refused(self):
        tampered = os.path.join(self.folder, "tampered.exe")
        shutil.copy(SIGNED_EXE, tampered)
        with open(tampered, "r+b") as handle:
            handle.seek(0x400)
            original = handle.read(1)
            handle.seek(0x400)
            handle.write(bytes([original[0] ^ 0xFF]))
        self.assertFalse(self.check(tampered)[1])

    def test_the_organization_has_to_match_exactly(self):
        for value, expected in (
            ("Microsoft Corporation", True),
            ("Microsoft Corporation Ltd", False),
            ("Not Microsoft Corporation", False),
            ("microsoft corporation", False),
            ("", False),
            (None, False),
        ):
            with self.subTest(organization=value):
                with patch.object(trust, "signer_organization", return_value=value):
                    self.assertEqual(trust.is_trusted_signature(object()), expected)

    def test_checking_a_signature_never_starts_another_program(self):
        with patch.object(subprocess.Popen, "__init__", side_effect=AssertionError("no process may be started")):
            self.assertTrue(trust.is_signed_by_microsoft(SIGNED_EXE))
            self.assertFalse(trust.is_signed_by_microsoft(self.fake_source()))


class ProtectedDirectoryTests(Workspace):
    def acl_entries(self, path):
        descriptor = win32security.GetNamedSecurityInfo(
            path, win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION,
        )
        dacl = descriptor.GetSecurityDescriptorDacl()
        sids = [win32security.ConvertSidToStringSid(dacl.GetAce(i)[2]) for i in range(dacl.GetAceCount())]
        return sids, descriptor.GetSecurityDescriptorControl()[0]

    def test_only_system_and_administrators_have_access_and_inheritance_is_blocked(self):
        sids, control = self.acl_entries(self.make_protected())
        self.assertEqual(sorted(sids), ["S-1-5-18", "S-1-5-32-544"])
        self.assertTrue(control & win32security.SE_DACL_PROTECTED)

    def test_extra_users_are_only_added_when_asked_for(self):
        sids, _control = self.acl_entries(self.make_protected(extra_sids=(self.me,)))
        self.assertIn(self.me, sids)

    def test_every_directory_has_a_new_random_name_inside_the_root(self):
        first, second = self.make_protected(), self.make_protected()
        self.assertNotEqual(first, second)
        for path in (first, second):
            self.assertEqual(os.path.dirname(path), self.folder)
            self.assertTrue(os.path.basename(path).startswith("ram-h64-"))

    def test_the_default_location_is_inside_the_windows_folder(self):
        self.assertEqual(
            os.path.normcase(trust.get_protected_root()),
            os.path.normcase(os.path.join(win32api.GetWindowsDirectory(), "Temp")),
        )

    def test_an_unusable_root_is_reported_as_a_verification_error(self):
        with self.assertRaises(trust.Handle64VerificationError):
            trust.create_protected_directory(os.path.join(self.folder, "missing", "deeper"))


@unittest.skipUnless(SIGNED_EXE, "needs a Microsoft binary with an embedded signature")
class TrustedExecutableTests(Workspace):
    def test_the_copy_lives_in_the_protected_folder_and_matches_the_source(self):
        source = self.signed_source()
        executable = self.trusted(source)
        self.assertEqual(os.path.dirname(os.path.dirname(executable)), self.folder)
        self.assertNotEqual(os.path.normcase(executable), os.path.normcase(source))
        with open(source, "rb") as a, open(executable, "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_the_same_content_reuses_one_copy_whatever_the_path(self):
        first = self.trusted(self.signed_source())
        other = os.path.join(self.folder, "elsewhere.exe")
        shutil.copy(SIGNED_EXE, other)
        self.assertEqual(self.trusted(other), first)
        self.assertEqual(len([n for n in os.listdir(self.folder) if n.startswith("ram-h64-")]), 1)

    def test_an_unsigned_source_is_refused_and_leaves_nothing_behind(self):
        with self.assertRaises(trust.Handle64VerificationError):
            self.trusted(self.fake_source())
        self.assertEqual([n for n in os.listdir(self.folder) if n.startswith("ram-h64-")], [])

    def test_a_missing_source_is_refused(self):
        with self.assertRaises(trust.Handle64VerificationError):
            self.trusted(os.path.join(self.folder, "nope.exe"))

    def test_a_source_someone_else_has_open_for_writing_is_refused(self):
        source = self.signed_source()
        with open(source, "ab"):
            with self.assertRaises(trust.Handle64VerificationError):
                self.trusted(source)

    def test_a_copy_that_does_not_match_is_refused_and_removed(self):
        original = trust._write_new_file
        with patch.object(trust, "_write_new_file", side_effect=lambda d, data: original(d, data[:-1] + b"X")):
            with self.assertRaises(trust.Handle64VerificationError):
                self.trusted(self.signed_source())
        self.assertEqual([n for n in os.listdir(self.folder) if n.startswith("ram-h64-")], [])

    def test_releasing_removes_the_copies_and_they_are_made_again_when_needed(self):
        source = self.signed_source()
        first = self.trusted(source)
        trust.release_trusted_copies()
        self.assertFalse(os.path.exists(os.path.dirname(first)))
        self.assertTrue(os.path.isfile(self.trusted(source)))


class RunHandle64Tests(Workspace):
    def patched_protection(self):
        def create(root, extra_sids=()):
            path = REAL_CREATE_PROTECTED(self.folder, (*extra_sids, self.me))
            self.created.append(path)
            return path

        return patch.object(trust, "create_protected_directory", side_effect=create)

    def test_the_trusted_copy_runs_with_its_own_folder_and_a_system_only_path(self):
        source = self.fake_source()
        with patch.object(trust, "is_trusted_signature", return_value=True), self.patched_protection(), \
                patch.object(actions.subprocess, "run", return_value=MagicMock(returncode=0)) as run:
            actions.run_handle64(source, ["-accepteula", "-p", "7"], timeout=5)
        command = run.call_args.args[0]
        self.assertEqual(command[1:], ["-accepteula", "-p", "7"])
        self.assertEqual(os.path.dirname(os.path.dirname(command[0])), self.folder)
        self.assertEqual(run.call_args.kwargs["cwd"], os.path.dirname(command[0]))
        system_folders = os.pathsep.join((win32api.GetSystemDirectory(), win32api.GetWindowsDirectory()))
        self.assertEqual(run.call_args.kwargs["env"]["PATH"], system_folders)
        self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_an_unverified_file_is_never_run(self):
        with patch.object(trust, "is_trusted_signature", return_value=False), self.patched_protection(), \
                patch.object(actions.subprocess, "run") as run:
            with self.assertRaises(actions.Handle64VerificationError):
                actions.run_handle64(self.fake_source(), [])
        run.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32" and os.path.exists(CMD_EXE), "needs Windows")
    def test_the_copy_really_runs(self):
        source = os.path.join(self.folder, "handle64.exe")
        shutil.copy(CMD_EXE, source)
        with patch.object(trust, "is_trusted_signature", return_value=True), self.patched_protection():
            result = actions.run_handle64(
                source, ["/c", "exit", "7"], creationflags=subprocess.CREATE_NO_WINDOW, timeout=30,
            )
        self.assertEqual(result.returncode, 7)


@unittest.skipUnless(SIGNED_EXE, "needs a Microsoft binary with an embedded signature")
class BypassRegressionTests(Workspace):
    def patched_protection(self):
        def create(root, extra_sids=()):
            path = REAL_CREATE_PROTECTED(self.folder, (*extra_sids, self.me))
            self.created.append(path)
            return path

        return patch.object(trust, "create_protected_directory", side_effect=create)

    def make_junction(self, link, target):
        REAL_RUN(["cmd", "/c", "mklink", "/J", link, target], check=True, capture_output=True)

    def test_a_hijacked_powershell_cannot_make_an_unsigned_file_pass(self):
        trap = os.path.join(self.folder, "trap")
        os.makedirs(os.path.join(trap, "Fake.Module"))
        shutil.copy(CMD_EXE, os.path.join(trap, "powershell.exe"))
        hostile = {"PATH": trap + os.pathsep + os.environ["PATH"], "PSModulePath": trap}
        previous = os.getcwd()
        os.chdir(trap)
        self.addCleanup(os.chdir, previous)
        unsigned = self.fake_source()
        with patch.dict(os.environ, hostile), \
                patch.object(subprocess.Popen, "__init__", side_effect=AssertionError("no process may be started")):
            with self.assertRaises(trust.Handle64VerificationError):
                self.trusted(unsigned)
            self.assertTrue(self.trusted(self.signed_source()))

    def test_swapping_a_parent_junction_cannot_redirect_the_execution(self):
        signed_dir = os.path.join(self.folder, "signed")
        evil_dir = os.path.join(self.folder, "evil")
        os.makedirs(signed_dir)
        os.makedirs(evil_dir)
        shutil.copy(SIGNED_EXE, os.path.join(signed_dir, "handle64.exe"))
        with open(os.path.join(evil_dir, "handle64.exe"), "wb") as handle:
            handle.write(b"MZ-unsigned-payload")
        junction = os.path.join(self.folder, "link")
        self.make_junction(junction, signed_dir)
        launched = {}

        def swap_then_record(command, **kwargs):
            os.rmdir(junction)
            self.make_junction(junction, evil_dir)
            launched["junction_now_points_to"] = os.path.realpath(junction)
            launched["command"] = command[0]
            with open(command[0], "rb") as handle:
                launched["content"] = handle.read()
            return MagicMock(returncode=0)

        with self.patched_protection(), patch.object(actions.subprocess, "run", side_effect=swap_then_record):
            actions.run_handle64(os.path.join(junction, "handle64.exe"), ["-p", "1"])

        self.assertEqual(os.path.normcase(launched["junction_now_points_to"]), os.path.normcase(evil_dir))
        self.assertEqual(os.path.dirname(os.path.dirname(launched["command"])), self.folder)
        self.assertFalse(os.path.normcase(launched["command"]).startswith(os.path.normcase(junction)))
        with open(SIGNED_EXE, "rb") as handle:
            self.assertEqual(launched["content"], handle.read())


class UseSitesTests(unittest.TestCase):
    def test_querying_handles_refuses_an_unverified_executable(self):
        error = actions.Handle64VerificationError("C:/x/handle64.exe is not signed by Microsoft Corporation.")
        with patch.object(actions, "run_handle64", side_effect=error):
            handles, code, output = actions._mr_h64_query_handles("C:/x/handle64.exe", 123)
        self.assertEqual((handles, code), ([], -1))
        self.assertIn("not signed by Microsoft", output)

    def test_closing_handles_refuses_an_unverified_executable(self):
        error = actions.Handle64VerificationError("not signed")
        with patch.object(actions, "run_handle64", side_effect=error):
            closed = actions._mr_h64_close_handle_values(
                123, [("1A", r"\Sessions\1\BaseNamedObjects\x")], "C:/x/handle64.exe", None
            )
        self.assertFalse(closed)

    def test_handle64_mode_does_not_start_with_an_unverified_file(self):
        windll = MagicMock()
        windll.shell32.IsUserAnAdmin.return_value = 1
        with patch.object(actions.ctypes, "windll", windll), \
                patch.object(actions, "find_handle64", return_value="C:/x/handle64.exe"), \
                patch.object(actions, "verify_handle64", return_value=False):
            self.assertEqual(actions.enable_multi_roblox("handle64"), (False, "HANDLE64_UNVERIFIED"))

    def test_stopping_the_mode_releases_the_protected_copies(self):
        with patch.object(actions.handle64_trust, "release_trusted_copies") as release, \
                patch.object(actions, "_mr_h64_path", "C:/x/handle64.exe"), \
                patch.object(actions, "_mr_handle", None):
            actions.disable_multi_roblox()
        release.assert_called_once()


class DownloadTests(unittest.TestCase):
    def archive(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("handle64.exe", b"MZ-fake")
            archive.writestr("handle.exe", b"MZ-fake")
        return buffer.getvalue()

    def run_download(self, signed):
        with tempfile.TemporaryDirectory() as folder:
            response = MagicMock(content=self.archive())
            with patch.object(actions, "_DATA_DIR", folder), \
                    patch.object(actions.requests, "get", return_value=response) as get, \
                    patch.object(actions.handle64_trust, "is_signed_by_microsoft", return_value=signed):
                result = actions.download_handle64()
            return result, os.path.exists(os.path.join(folder, "handle64.exe")), get

    def test_signed_download_is_installed(self):
        result, installed, get = self.run_download(True)
        self.assertTrue(result)
        self.assertTrue(installed)
        self.assertIn("timeout", get.call_args.kwargs)

    def test_unsigned_download_is_discarded(self):
        result, installed, _ = self.run_download(False)
        self.assertFalse(result)
        self.assertFalse(installed)


class LockHelperTests(Workspace):
    def test_the_file_cannot_be_changed_while_locked_and_is_free_afterwards(self):
        path = self.fake_source()
        outcomes = {}
        with trust.open_locked(path):
            for label, action in (
                ("write", lambda: open(path, "ab")),
                ("delete", lambda: os.remove(path)),
                ("rename", lambda: os.rename(path, path + ".moved")),
                ("rename folder", lambda: os.rename(self.folder, self.folder + "_moved")),
            ):
                try:
                    action()
                    outcomes[label] = "allowed"
                except OSError:
                    outcomes[label] = "blocked"
        self.assertEqual(set(outcomes.values()), {"blocked"})
        with open(path, "ab") as handle:
            handle.write(b"ok")

    def test_reading_returns_the_whole_file(self):
        data = os.urandom(trust._READ_CHUNK + 123)
        path = self.fake_source(data)
        with trust.open_locked(path) as handle:
            self.assertEqual(trust.read_all(handle), data)


if __name__ == "__main__":
    unittest.main()
