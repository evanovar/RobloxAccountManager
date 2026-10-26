import os
import collections
import tempfile
import unittest
from unittest.mock import patch
from features import diagnostics

class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(diagnostics, "_RECENT_LINES", collections.deque(maxlen=500)))
        self.enterContext(patch.object(diagnostics, "_CONSOLE_QUEUE", collections.deque(maxlen=2000)))

    def test_sensitive_values_are_redacted(self):
        text = (
            ".ROBLOSECURITY=secret-cookie; "
            "'password': 'secret-password' "
            "link code: private-server-code "
            "https://discord.com/api/webhooks/123/secret-token"
        )
        redacted = diagnostics.redact(text)
        self.assertNotIn("secret-cookie", redacted)
        self.assertNotIn("secret-password", redacted)
        self.assertNotIn("private-server-code", redacted)
        self.assertNotIn("secret-token", redacted)

    def test_console_includes_the_recorded_timestamp_and_preserves_color_and_redaction(self):
        with patch.object(diagnostics, '_timestamp', return_value='2026-10-26 14:05:06.123'):
            diagnostics._record_line('[WARNING] .ROBLOSECURITY=synthetic-secret', 'stderr')

        text, color = diagnostics.console_queue().popleft()
        self.assertEqual(text, '[2026-10-26 14:05:06.123] [WARNING] .ROBLOSECURITY=[REDACTED]')
        self.assertEqual(color, '#FFA726')
        self.assertEqual(
            diagnostics.get_recent_lines()[-1],
            '[2026-10-26 14:05:06.123] [stderr] [WARNING] .ROBLOSECURITY=[REDACTED]',
        )

    def test_stream_timestamps_complete_lines_and_flushed_partial_lines(self):
        stream = diagnostics.DiagnosticStream(None, 'stdout')
        with patch.object(diagnostics, '_timestamp', side_effect=(
            '2026-10-26 14:05:06.123', '2026-10-26 14:05:07.456',
        )):
            stream.write('[INFO] First')
            self.assertFalse(diagnostics.console_queue())
            stream.write(' line\nSecond line')
            stream.flush()

        self.assertEqual(list(diagnostics.console_queue()), [
            ('[2026-10-26 14:05:06.123] [INFO] First line', '#5BB8FF'),
            ('[2026-10-26 14:05:07.456] Second line', None),
        ])

    def test_crash_report_contains_traceback_and_redacts_console(self):
        with tempfile.TemporaryDirectory() as work_dir:
            crash_path = os.path.join(work_dir, "crash.log")
            diagnostics._RECENT_LINES.clear()
            diagnostics._record_line(
                ".ROBLOSECURITY=private-cookie",
                "test",
            )
            try:
                raise RuntimeError("test crash")
            except RuntimeError as exc:
                with patch(
                    "features.diagnostics._build_crash_path",
                    return_value=crash_path,
                ):
                    result_path = diagnostics.report_exception(
                        "Reliability test",
                        exc,
                        fatal=True,
                    )

            self.assertEqual(result_path, crash_path)
            with open(crash_path, "r", encoding="utf-8") as handle:
                report = handle.read()
            self.assertIn("RuntimeError: test crash", report)
            self.assertNotIn("private-cookie", report)

    def test_launch_urls_are_redacted_in_windows_errors_and_console_logs(self):
        url = "roblox-player:1+launchmode:play+gameinfo:SYNTHETIC-TICKET+placelauncherurl:https://example.com/?linkCode=PRIVATE-CODE"
        for text in (f"Application not found: '{url}'", f"Launch failed: {url}", f'Launch failed: "{url.upper()}"'):
            with self.subTest(text=text):
                redacted = diagnostics.redact(text)
                self.assertIn("[REDACTED ROBLOX LAUNCH URL]", redacted)
                self.assertNotIn("SYNTHETIC-TICKET", redacted)
                self.assertNotIn("PRIVATE-CODE", redacted)
        diagnostics._record_line(f"Launch failed: {url}", "test")
        self.assertNotIn("SYNTHETIC-TICKET", diagnostics._RECENT_LINES[-1])


class UIHangDiagnosticsTests(unittest.TestCase):
    def test_hang_report_has_thread_locations_without_local_values(self):
        private_value = 'secret-test-value-never-write'
        with tempfile.TemporaryDirectory() as directory, patch.object(
            diagnostics, '_get_diagnostics_root', return_value=directory,
        ), patch.object(diagnostics, 'record_message'):
            path = diagnostics.report_ui_stall(35)
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding='utf-8') as handle:
                report = handle.read()
            self.assertIn('MainThread', report)
            self.assertIn('report_ui_stall', report)
            self.assertNotIn(private_value, report)
