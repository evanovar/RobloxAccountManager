import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StartupImportTests(unittest.TestCase):
    def test_avatar_executor_works_when_qt_is_imported_first(self):
        root = Path(__file__).resolve().parents[2]
        script = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from PySide6.QtWidgets import QApplication
app = QApplication([])
from features import avatars
assert avatars._EXECUTOR.submit(lambda: 42).result(timeout=5) == 42
avatars._EXECUTOR.shutdown(wait=True)
"""
        with tempfile.TemporaryDirectory() as profile:
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=root,
                env=dict(os.environ, QT_QPA_PLATFORM="offscreen", RAM_DATA_DIR=profile),
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
