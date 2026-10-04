import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from features import roblox_settings as settings
from features import settings_store


def write_xml(path, volume):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<roblox version="4"><Item class="UserGameSettings"><Properties>'
        f'<float name="MasterVolume">{volume}</float>'
        '<int name="FramerateCap">60</int>'
        '</Properties></Item></roblox>', encoding="utf-8",
    )


class RobloxSettingsPathTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory)
        self.default = self.root / "LocalAppData" / "Roblox" / "GlobalBasicSettings_13.xml"
        self.custom = self.root / "Custom location 中文" / "CustomSettings.xml"
        write_xml(self.default, "0.8")
        write_xml(self.custom, "0.6")
        self.enterContext(patch.dict(os.environ, {"LOCALAPPDATA": str(self.default.parent.parent)}))
        self.enterContext(patch.object(settings, "get_data_dir", return_value=str(self.root / "Data")))
        self.enterContext(patch.object(settings_store, "_SETTINGS_PATH", str(self.root / "Data" / "ui_settings.json")))
        settings_store.invalidate()
        settings._clear_auto_apply_cache()
        self.addCleanup(settings_store.invalidate)
        self.addCleanup(settings._clear_auto_apply_cache)
        self.addCleanup(self.make_files_writable)

    def make_files_writable(self):
        for path in self.root.rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)

    def profile(self):
        result = settings.load_local_profile()
        self.assertTrue(result, result.detail)
        return result.data["profile"]

    def volume(self, path):
        return ET.parse(path).find('.//float[@name="MasterVolume"]').text

    def test_default_location_is_used_without_an_override(self):
        self.assertEqual(settings.get_settings_path(), self.default)
        self.assertEqual(settings.load_settings().data["path"], str(self.default))

    def test_custom_path_persists_without_losing_other_ui_settings(self):
        settings_store.save("unrelated", "preserved")
        self.assertTrue(settings.set_settings_path(str(self.custom)))
        settings_store.invalidate()
        self.assertEqual(settings.get_settings_path(), self.custom)
        self.assertEqual(settings_store.get("unrelated"), "preserved")
        self.assertEqual(self.profile()["source"]["path"], str(self.custom))

    def test_custom_path_works_when_local_appdata_is_unavailable(self):
        with patch.dict(os.environ):
            os.environ.pop("LOCALAPPDATA", None)
            self.assertIsNone(settings.get_default_settings_path())
            self.assertTrue(settings.set_settings_path(str(self.custom)))
            self.assertEqual(settings.load_settings().data["path"], str(self.custom))

    def test_invalid_selections_do_not_change_the_saved_location(self):
        self.assertTrue(settings.set_settings_path(str(self.custom)))
        invalid_xml = self.root / "invalid.xml"
        invalid_xml.write_text("broken XML", encoding="utf-8")
        wrong_xml = self.root / "wrong.xml"
        wrong_xml.write_text("<unrelated/>", encoding="utf-8")
        for path in (self.root / "missing.xml", self.root, self.root / "file.txt", invalid_xml, wrong_xml):
            with self.subTest(path=path):
                result = settings.set_settings_path(str(path))
                self.assertFalse(result)
                self.assertEqual(settings.get_settings_path(), self.custom)
        self.assertEqual(self.volume(self.default), "0.8")

    def test_missing_custom_file_does_not_silently_edit_the_default(self):
        settings_store.save("roblox_settings_path", str(self.root / "missing.xml"))
        self.assertEqual(settings.load_settings().code, "ROBLOX_SETTINGS_NOT_FOUND")
        self.assertFalse(settings.set_framerate_cap(120))
        self.assertEqual(self.volume(self.default), "0.8")

    def test_manual_apply_and_backups_target_only_the_custom_xml(self):
        default_before = self.default.read_bytes()
        custom_before = self.custom.read_bytes()
        self.assertTrue(settings.set_settings_path(str(self.custom)))
        self.profile()
        self.assertTrue(settings.save_advanced_setting("MasterVolume", "0.2"))
        self.assertTrue(settings.apply_local_profile())
        self.assertEqual(self.volume(self.custom), "0.2")
        self.assertEqual(self.default.read_bytes(), default_before)
        self.assertEqual(Path(str(self.custom) + ".ram.bak").read_bytes(), custom_before)
        self.assertFalse(Path(str(self.default) + ".ram.bak").exists())

    def test_framerate_helper_uses_the_custom_location(self):
        self.assertTrue(settings.set_settings_path(str(self.custom)))
        self.assertTrue(settings.set_framerate_cap(144))
        self.assertEqual(ET.parse(self.custom).find('.//int[@name="FramerateCap"]').text, "144")
        self.assertEqual(ET.parse(self.default).find('.//int[@name="FramerateCap"]').text, "60")

    def test_path_change_loads_new_values_instead_of_old_pending_edits(self):
        self.profile()
        self.assertTrue(settings.save_advanced_setting("MasterVolume", "0.1"))
        self.assertTrue(settings.set_settings_path(str(self.custom)))
        self.assertEqual(self.profile()["settings"]["MasterVolume"]["value"], "0.6")
        self.assertTrue(settings.set_settings_path(""))
        self.assertEqual(self.profile()["settings"]["MasterVolume"]["value"], "0.8")
        self.assertIsNone(settings_store.get("roblox_settings_path"))

    def test_selecting_the_same_location_keeps_pending_edits_and_owned_lock(self):
        self.profile()
        self.assertTrue(settings.save_advanced_setting("MasterVolume", "0.1"))
        profile = self.profile()
        profile["lock_owned"] = True
        settings.save_local_profile(profile)
        settings._set_read_only(self.default, True)
        result = settings.set_settings_path(str(self.default))
        self.assertTrue(result)
        self.assertFalse(result.data["changed"])
        self.assertEqual(self.profile()["settings"]["MasterVolume"]["value"], "0.1")
        self.assertFalse(self.default.stat().st_mode & stat.S_IWRITE)

    def test_owned_lock_is_released_without_transferring_ownership(self):
        profile = self.profile()
        profile["lock_owned"] = True
        settings.save_local_profile(profile)
        settings._set_read_only(self.default, True)
        settings._set_read_only(self.custom, True)
        self.assertTrue(settings.set_settings_path(str(self.custom)))
        self.assertTrue(self.default.stat().st_mode & stat.S_IWRITE)
        self.assertFalse(self.profile()["lock_owned"])
        self.assertTrue(settings.apply_local_profile())
        self.assertFalse(self.custom.stat().st_mode & stat.S_IWRITE)

    def test_external_read_only_flag_is_preserved_on_the_previous_file(self):
        self.profile()
        settings._set_read_only(self.default, True)
        self.assertTrue(settings.set_settings_path(str(self.custom)))
        self.assertFalse(self.default.stat().st_mode & stat.S_IWRITE)

    def test_failed_config_save_restores_the_original_location_and_lock(self):
        profile = self.profile()
        profile["lock_owned"] = True
        settings.save_local_profile(profile)
        settings._set_read_only(self.default, True)
        with patch.object(settings_store, "save", side_effect=PermissionError("settings locked")):
            result = settings.set_settings_path(str(self.custom))
        self.assertFalse(result)
        self.assertEqual(settings.get_settings_path(), self.default)
        self.assertFalse(self.default.stat().st_mode & stat.S_IWRITE)
        self.assertTrue(self.profile()["lock_owned"])

    def test_reset_is_allowed_even_if_default_xml_does_not_exist(self):
        self.assertTrue(settings.set_settings_path(str(self.custom)))
        self.default.unlink()
        self.assertTrue(settings.set_settings_path(""))
        self.assertEqual(settings.get_settings_path(), self.default)
        self.assertEqual(settings.load_settings().code, "ROBLOX_SETTINGS_NOT_FOUND")

    def test_auto_apply_uses_custom_path_after_restart(self):
        default_before = self.default.read_bytes()
        self.assertTrue(settings.set_settings_path(str(self.custom)))
        self.profile()
        self.assertTrue(settings.save_advanced_setting("MasterVolume", "0.3"))
        self.assertTrue(settings.save_advanced_auto_apply(True))
        settings_store.invalidate()
        settings._clear_auto_apply_cache()
        result = settings.apply_saved_customizations()
        self.assertTrue(result, result.detail)
        self.assertEqual(result.data["path"], str(self.custom))
        self.assertEqual(self.volume(self.custom), "0.3")
        self.assertFalse(self.custom.stat().st_mode & stat.S_IWRITE)
        self.assertEqual(self.default.read_bytes(), default_before)
        self.assertTrue(settings.set_settings_path(""))
        self.assertTrue(self.custom.stat().st_mode & stat.S_IWRITE)
        self.assertTrue(self.profile()["advanced_auto_apply"])

    def test_path_selection_runs_on_a_background_thread(self):
        finished = threading.Event()
        callback_threads = []

        def callback(result):
            callback_threads.append((threading.get_ident(), result))
            finished.set()

        settings.set_settings_path_async(str(self.custom), callback)
        self.assertTrue(finished.wait(3))
        self.assertNotEqual(callback_threads[0][0], threading.get_ident())
        self.assertTrue(callback_threads[0][1])
