import base64
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from features import settings_store
from features import theme_model as model
from features import theme_library as library_module


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=')
GIF = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
BMP = base64.b64decode('Qk1GAAAAAAAAADYAAAAoAAAAAgAAAAIAAAABABgAAAAAABAAAABhDwAAYQ8AAAAAAAAAAAAARCLMRCLMAABEIsxEIswAAA==')
WEBP = base64.b64decode('UklGRjgAAABXRUJQVlA4ICwAAABwAQCdASoCAAIAAgA0JaACdAFAAAD+71EsYsPDa//srH/+lY//0rH7lAAAAA==')
JPEG = base64.b64decode(
    '/9j/4AAQSkZJRgABAQEAZABkAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/'
    '2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/'
    'wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKB'
    'kaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm'
    'p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA'
    'AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm'
    'Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/'
    '9oADAMBAAIRAxEAPwDmKKKK5D9JP//Z'
)


def riff_chunk(kind, payload):
    return kind + struct.pack('<I', len(payload)) + payload + b'\0' * (len(payload) % 2)


def avi_fixture():
    avih = struct.pack('<14I', 100000, 10000, 0, 16, 1, 0, 1, 4096, 2, 2, 0, 0, 0, 0)
    strh = struct.pack('<4s4sIHH8I4h', b'vids', b'MJPG', 0, 0, 0, 0, 1, 10, 0, 1, 4096, 0xffffffff, 0, 0, 0, 2, 2)
    strf = struct.pack('<IiiHH4sIiiII', 40, 2, 2, 1, 24, b'MJPG', 16, 0, 0, 0, 0)
    header = riff_chunk(b'LIST', b'hdrl' + riff_chunk(b'avih', avih) +
                        riff_chunk(b'LIST', b'strl' + riff_chunk(b'strh', strh) + riff_chunk(b'strf', strf)))
    return riff_chunk(b'RIFF', b'AVI ' + header + riff_chunk(b'LIST', b'movi' + riff_chunk(b'00dc', JPEG)))


def png_chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))


def atom(kind, payload):
    return struct.pack('>I4s', len(payload) + 8, kind) + payload


def ebml_element(identifier, payload, unknown=False):
    identifier = identifier.to_bytes((identifier.bit_length() + 7) // 8, 'big')
    length = b'\xff' if unknown else (0x80 | len(payload)).to_bytes(1, 'big') if len(payload) < 127 else (0x4000 | len(payload)).to_bytes(2, 'big')
    return identifier + length + payload


def webm_fixture(document_type=b'webm', clusters=1):
    track = (ebml_element(0xd7, b'\x01') + ebml_element(0x73c5, b'\x01') + ebml_element(0x83, b'\x01') +
             ebml_element(0x86, b'V_VP8') + ebml_element(0xe0, ebml_element(0xb0, b'\x02') + ebml_element(0xba, b'\x02')))
    block = ebml_element(0xa3, b'\x81\0\0\x80' + WEBP[20:])
    segment = ebml_element(0x1654ae6b, ebml_element(0xae, track)) + ebml_element(0x1f43b675, ebml_element(0xe7, b'\0') + block, True) * clusters
    return ebml_element(0x1a45dfa3, ebml_element(0x4282, document_type)) + ebml_element(0x18538067, segment, True)


class ThemeLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path_patch = patch.object(settings_store, '_SETTINGS_PATH', str(self.root / 'ui_settings.json'))
        self.path_patch.start()
        settings_store.invalidate()
        self.library = library_module.ThemeLibrary(self.root)
        self.media = self.root / 'source.png'
        self.media.write_bytes(PNG)

    def tearDown(self):
        settings_store.invalidate()
        self.path_patch.stop()
        self.temp.cleanup()

    def draft(self, media=False):
        theme = model.builtin_theme('default')
        theme.name = 'Example'
        if media:
            theme.background = model.Background(True, str(self.media), 20, 40, '#181818')
        return theme

    def package(self, data=None, extra=None):
        path = self.root / 'theme.ramtheme'
        data = data if data is not None else model.theme_to_dict(self.draft())
        data.pop('id', None)
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('theme.json', json.dumps(data))
            for name, content in (extra or {}).items():
                archive.writestr(name, content)
        return path

    def test_drafts_do_not_mutate_builtins_or_saved_documents(self):
        draft = self.draft()
        draft.set_color('TEXT', '#123456')
        saved = self.library.save(draft, '  My colors  ')
        self.assertEqual(saved.name, 'My colors')
        self.assertFalse(saved.id.startswith('builtin:'))
        saved.colors['TEXT'] = '#FFFFFF'
        self.assertEqual(self.library.load(saved.id).colors['TEXT'], '#123456')
        self.assertEqual(model.builtin_theme('default').colors['TEXT'], '#EDEDED')
        reloaded = self.library.load(saved.id)
        reloaded.set_color('TEXT', '#ABCDEF')
        self.assertEqual(self.library.save(reloaded).id, saved.id)
        self.assertEqual(reloaded.starting_colors['TEXT'], '#EDEDED')

    def test_colors_regenerate_only_dependent_defaults_and_reset_exact_start(self):
        theme = self.draft()
        theme.set_color('ACCENT_SOFT', '#112233')
        theme.set_color('ACCENT', '#FF0000')
        self.assertEqual(theme.colors['ACCENT_HOVER'], '#FF2626')
        self.assertEqual(theme.colors['ACCENT_SOFT'], '#112233')
        self.assertEqual(theme.colors['HOVER'], '#3A3A3A')
        theme.reset_color('ACCENT')
        self.assertEqual(theme.colors['ACCENT_HOVER'], '#1A8FE0')
        self.assertEqual(theme.colors['ACCENT_SOFT'], '#112233')
        theme.reset_color('ACCENT_SOFT')
        self.assertEqual(theme.colors['ACCENT_SOFT'], '#3A5A9A')
        self.assertNotIn('ACCENT_SOFT', theme.customized)
        theme.set_color('INPUT', '#FFFFFF')
        self.assertNotEqual(theme.colors['HOVER'], '#3A3A3A')
        with self.assertRaises(model.ThemeError):
            theme.set_color('TEXT', 'red')

    def test_save_copies_assets_and_replacement_removes_only_owned_old_media(self):
        saved = self.library.save(self.draft(True))
        owned = Path(saved.background.path)
        self.assertTrue(owned.is_relative_to(self.root / 'themes' / saved.id))
        self.media.unlink()
        self.assertEqual(owned.read_bytes(), PNG)
        saved.background.path = ''
        saved.background.enabled = False
        updated = self.library.save(saved)
        self.assertFalse(owned.exists())
        self.assertEqual(updated.background.path, '')

    def test_failed_write_preserves_document_media_and_active_selection(self):
        saved = self.library.save(self.draft(True))
        self.library.activate(saved.id)
        previous = (self.root / 'themes' / saved.id / 'theme.json').read_bytes()
        changed = saved.clone()
        changed.colors['TEXT'] = '#123456'
        changed.background.path = ''
        changed.background.enabled = False
        with patch.object(library_module, 'write_json_atomic', side_effect=OSError('disk full')):
            with self.assertRaises(model.ThemeError):
                self.library.save(changed)
        self.assertEqual((self.root / 'themes' / saved.id / 'theme.json').read_bytes(), previous)
        self.assertTrue(Path(saved.background.path).exists())
        self.assertEqual(settings_store.get('active_theme'), saved.id)

    def test_round_trip_import_is_independent_and_staging_is_owned(self):
        theme = self.draft(True)
        theme.set_color('ACCENT_SOFT', '#112233')
        destination = self.root / 'portable.ramtheme'
        self.library.export_theme(theme, destination)
        self.media.unlink()
        imported = self.library.import_theme(destination)
        self.assertEqual(imported.id, '')
        self.assertEqual(imported.colors, theme.colors)
        self.assertEqual(imported.starting_colors, theme.starting_colors)
        self.assertEqual(imported.customized, {'ACCENT_SOFT'})
        self.assertEqual(Path(imported.background.path).read_bytes(), PNG)
        self.assertIsNone(settings_store.get('active_theme'))
        staging = Path(imported.background.path)
        saved = self.library.save(imported)
        self.library.discard_import(imported)
        self.assertFalse(staging.exists())
        self.assertTrue(Path(saved.background.path).exists())

    def test_import_rejects_invalid_manifest_and_hostile_paths(self):
        for version, colors in ((2, self.draft().colors), (1, {'TEXT': 'red'})):
            data = model.theme_to_dict(self.draft())
            data.update(version=version, colors=colors)
            with self.subTest(version=version), self.assertRaises(model.ThemeError):
                self.library.import_theme(self.package(data))
        for name in ('../escape.png', '/absolute.png', 'C:/outside.png', 'extra.exe', 'folder\\escape.png'):
            with self.subTest(name=name), self.assertRaises(model.ThemeError):
                self.library.import_theme(self.package(extra={name: b'MZ'}))
        self.assertEqual(len(self.library.list_themes()), 8)

    def test_import_rejects_mismatch_links_duplicates_and_size_limits(self):
        data = model.theme_to_dict(self.draft(True))
        data['background']['path'] = 'background.png'
        with self.assertRaises(model.ThemeError):
            self.library.import_theme(self.package(data, {'background.png': b'MZexecutable'}))
        path = self.package()
        with zipfile.ZipFile(path, 'a') as archive:
            info = zipfile.ZipInfo('link.png')
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            archive.writestr(info, 'target')
        with self.assertRaises(model.ThemeError):
            self.library.import_theme(path)
        path = self.package()
        with zipfile.ZipFile(path, 'a') as archive:
            with self.assertWarns(UserWarning):
                archive.writestr('theme.json', '{}')
        with self.assertRaises(model.ThemeError):
            self.library.import_theme(path)
        with patch.object(library_module, 'MAX_MANIFEST_BYTES', 10):
            with self.assertRaises(model.ThemeError):
                self.library.import_theme(self.package())
        with patch.object(library_module, 'MAX_MEDIA_BYTES', 10):
            with self.assertRaises(model.ThemeError):
                self.library.import_theme(self.package(data, {'background.png': PNG}))

    def test_export_failure_leaves_existing_destination(self):
        destination = self.root / 'portable.ramtheme'
        destination.write_bytes(b'previous package')
        with patch.object(library_module.os, 'replace', side_effect=OSError('locked')):
            with self.assertRaises(model.ThemeError):
                self.library.export_theme(self.draft(), destination)
        self.assertEqual(destination.read_bytes(), b'previous package')

    def test_import_rejects_corrupt_media_even_when_signature_is_valid(self):
        corrupted = bytearray(PNG)
        corrupted[45] ^= 1
        data = model.theme_to_dict(self.draft(True))
        data['background']['path'] = 'background.png'
        with self.assertRaises(model.ThemeError):
            self.library.import_theme(self.package(data, {'background.png': corrupted}))

    def test_import_rejects_null_bytes_in_original_archive_entry_names(self):
        path = self.root / 'nul-name.ramtheme'
        data = model.theme_to_dict(self.draft())
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('theme.jsonXevil.exe', json.dumps(data))
        path.write_bytes(path.read_bytes().replace(b'theme.jsonXevil.exe', b'theme.json\x00evil.exe'))
        with self.assertRaises(model.ThemeError):
            self.library.import_theme(path)

    def test_portable_document_excludes_installation_ids_paths_and_recovery(self):
        theme = self.draft(True)
        theme.recovery = {'legacy_background_path': 'C:/old-private-location.png'}
        package = self.root / 'portable.ramtheme'
        self.library.export_theme(theme, package)
        with zipfile.ZipFile(package) as archive:
            manifest = json.loads(archive.read('theme.json'))
        self.assertNotIn('id', manifest)
        self.assertNotIn('recovery', manifest)
        self.assertEqual(manifest['background']['path'], 'background.png')

    def test_import_supports_gif_and_ignores_unknown_optional_document_fields(self):
        gif = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
        data = model.theme_to_dict(self.draft(True))
        data['background']['path'] = 'background.gif'
        data['future_optional_metadata'] = {'anything': 'allowed'}
        theme = self.library.import_theme(self.package(data, {'background.gif': gif}))
        self.assertEqual(Path(theme.background.path).read_bytes(), gif)
        self.library.discard_import(theme)

    def test_import_rejects_empty_gif_without_changing_active_saved_theme(self):
        saved = self.library.save(self.draft())
        self.library.activate(saved.id)
        data = model.theme_to_dict(self.draft(True))
        data['background']['path'] = 'background.gif'
        for content in (b'GIF89a\x01\x00\x01\x00\x00\x00\x00;', GIF[:-3] + b';'):
            with self.subTest(content=content), self.assertRaises(model.ThemeError):
                self.library.import_theme(self.package(data, {'background.gif': content}))
            self.assertEqual(settings_store.get('active_theme'), saved.id)
        self.assertEqual(len(self.library.list_themes()), 9)

    def test_import_rejects_valid_header_with_truncated_video_container(self):
        saved = self.library.save(self.draft())
        self.library.activate(saved.id)
        truncated = {
            'mp4': struct.pack('>I4s4sI4s', 20, b'ftyp', b'isom', 0, b'isom') + struct.pack('>I4s', 1024, b'mdat') + b'x',
            'avi': b'RIFF' + struct.pack('<I', 1024) + b'AVI LIST' + b'\0' * 8,
            'webm': b'\x1aE\xdf\xa3\x9f\x42\x82\x84webm' + b'\0' * 4,
        }
        for suffix, content in truncated.items():
            data = model.theme_to_dict(self.draft(True))
            name = 'background.' + suffix
            data['background']['path'] = name
            with self.subTest(suffix=suffix), self.assertRaises(model.ThemeError):
                self.library.import_theme(self.package(data, {name: content}))
            self.assertEqual(settings_store.get('active_theme'), saved.id)

    def test_import_rejects_still_image_headers_without_complete_pixel_payload(self):
        invalid_png = PNG[:33] + png_chunk(b'IDAT', b'invalid deflate data') + png_chunk(b'IEND', b'')
        invalid = {
            'jpg': b'\xff\xd8\xffno-frame-or-image-scan\xff\xd9',
            'bmp': BMP[:54],
            'webp': b'RIFF' + struct.pack('<I', 22) + b'WEBPVP8 ' + struct.pack('<I', 100) + b'\0' * 10,
            'png': invalid_png,
        }
        for suffix, content in invalid.items():
            data = model.theme_to_dict(self.draft(True))
            name = 'background.' + suffix
            data['background']['path'] = name
            with self.subTest(suffix=suffix), self.assertRaises(model.ThemeError):
                self.library.import_theme(self.package(data, {name: content}))

    def test_common_complete_media_fixtures_round_trip_through_packages(self):
        for suffix, content in {'png': PNG, 'gif': GIF, 'jpg': JPEG, 'bmp': BMP, 'webp': WEBP,
                                'avi': avi_fixture(), 'webm': webm_fixture(), 'mkv': webm_fixture(b'matroska')}.items():
            with self.subTest(suffix=suffix):
                data = model.theme_to_dict(self.draft(True))
                name = 'background.' + suffix
                data['background']['path'] = name
                theme = self.library.import_theme(self.package(data, {name: content}))
                self.assertEqual(Path(theme.background.path).read_bytes(), content)
                saved = self.library.save(theme)
                self.library.discard_import(theme)
                self.assertEqual(Path(saved.background.path).read_bytes(), content)

    def test_png_accepts_empty_split_idat_and_unused_trailing_compressed_bytes(self):
        compressed = PNG[41:52]
        content = (PNG[:33] + png_chunk(b'IDAT', b'') + png_chunk(b'IDAT', compressed[:3]) +
                   png_chunk(b'IDAT', compressed[3:] + b'unused') + png_chunk(b'IDAT', b'') + png_chunk(b'IEND', b''))
        data = model.theme_to_dict(self.draft(True))
        data['background']['path'] = 'background.png'
        theme = self.library.import_theme(self.package(data, {'background.png': content}))
        self.assertEqual(Path(theme.background.path).read_bytes(), content)
        self.library.discard_import(theme)

    def test_bmff_accepts_structural_video_with_newer_brand(self):
        handler = atom(b'hdlr', b'\0' * 8 + b'vide' + b'\0' * 12)
        content = (atom(b'ftyp', b'iso8' + b'\0' * 4 + b'isom') +
                   atom(b'moov', atom(b'trak', atom(b'mdia', handler))) + atom(b'mdat', JPEG))
        data = model.theme_to_dict(self.draft(True))
        data['background']['path'] = 'background.mp4'
        theme = self.library.import_theme(self.package(data, {'background.mp4': content}))
        self.assertEqual(Path(theme.background.path).read_bytes(), content)
        self.library.discard_import(theme)

    def test_unknown_length_webm_clusters_are_siblings_not_nested_containers(self):
        content = webm_fixture(clusters=24)
        data = model.theme_to_dict(self.draft(True))
        data['background']['path'] = 'background.webm'
        theme = self.library.import_theme(self.package(data, {'background.webm': content}))
        self.assertEqual(Path(theme.background.path).read_bytes(), content)
        self.library.discard_import(theme)

    def test_migration_retries_without_duplicates_or_overwriting_custom_edits(self):
        settings = {'accent_color': '#FF0000', 'other_setting': 42}
        settings_store.replace(settings)
        original = settings_store.save
        def fail_marker(key, value):
            if key == 'theme_migration_version':
                raise OSError('interrupted marker')
            return original(key, value)
        with patch.object(settings_store, 'save', side_effect=fail_marker):
            self.library.startup(settings)
        themes = [theme for theme in self.library.list_themes() if not theme.id.startswith('builtin:')]
        self.assertEqual(len(themes), 1)
        themes[0].set_color('TEXT', '#123456')
        self.library.save(themes[0])
        active = self.library.startup(settings_store.load())
        self.assertEqual(active.id, themes[0].id)
        self.assertEqual(active.colors['TEXT'], '#123456')
        self.assertEqual(settings_store.get('other_setting'), 42)
        self.assertEqual(settings_store.get('theme_migration_version'), 1)
        self.assertEqual(len(self.library.list_themes()), 9)

    def test_missing_legacy_media_preserves_colors_and_records_recovery(self):
        settings = {'color_theme': 'nord', 'custom_background': {
            'enabled': True, 'path': str(self.root / 'gone.png'), 'blur': 50,
            'text': '#123456', 'muted': '#223344', 'outline': '#334455', 'tint': '#445566'}}
        settings_store.replace(settings)
        theme = self.library.startup(settings)
        self.assertEqual(theme.name, 'My previous theme')
        self.assertEqual(theme.colors['TEXT'], '#123456')
        self.assertEqual(theme.background.dim, 31)
        self.assertFalse(theme.background.enabled)
        self.assertTrue(self.library.issues)
        document = json.loads((self.root / 'themes' / theme.id / 'theme.json').read_text())
        self.assertEqual(document['recovery']['legacy_background_path'], str(self.root / 'gone.png'))

    def test_plain_preset_migration_ignores_disabled_background_colors(self):
        settings = {'color_theme': 'nord', 'custom_background': {'enabled': False, 'text': '#123456'}}
        settings_store.replace(settings)
        theme = self.library.startup(settings)
        self.assertEqual(theme.id, 'builtin:nord')
        self.assertEqual(theme.colors['TEXT'], '#ECEFF4')

    def test_malformed_legacy_media_path_does_not_block_palette_migration(self):
        settings = {'accent_color': '#FF0000', 'custom_background': {
            'enabled': True, 'path': '\x00invalid.png', 'blur': float('inf'), 'text': 'red'}}
        settings_store.replace(settings)
        theme = self.library.startup(settings)
        self.assertEqual(theme.name, 'My previous theme')
        self.assertEqual(theme.colors['ACCENT'], '#FF0000')
        self.assertEqual(theme.colors['TEXT'], '#EDEDED')
        self.assertFalse(theme.background.enabled)
        self.assertEqual(settings_store.get('theme_migration_version'), 1)

    def test_committed_save_is_not_reported_as_failed_when_media_cleanup_fails(self):
        saved = self.library.save(self.draft())
        saved.set_color('TEXT', '#123456')
        directory = self.root / 'themes' / saved.id
        original = Path.iterdir
        def fail_cleanup(path):
            if path == directory:
                raise PermissionError('cleanup is temporarily unavailable')
            return original(path)
        with patch.object(Path, 'iterdir', fail_cleanup):
            result = self.library.save(saved)
        self.assertEqual(result.colors['TEXT'], '#123456')
        self.assertEqual(self.library.load(saved.id).colors['TEXT'], '#123456')
        self.assertTrue(self.library.issues)

    def test_failed_active_migration_write_is_retry_safe(self):
        settings = {'accent_color': '#FF0000'}
        settings_store.replace(settings)
        original = settings_store.save
        def fail_active(key, value):
            if key == 'active_theme':
                raise OSError('settings are temporarily locked')
            return original(key, value)
        with patch.object(settings_store, 'save', side_effect=fail_active):
            self.library.startup(settings)
        self.assertIsNone(settings_store.get('theme_migration_version'))
        self.assertEqual(len(self.library.list_themes()), 9)
        active = self.library.startup(settings_store.load())
        self.assertEqual(active.colors['ACCENT'], '#FF0000')
        self.assertEqual(settings_store.get('theme_migration_version'), 1)
        self.assertEqual(len(self.library.list_themes()), 9)

    def test_broken_custom_document_does_not_block_startup_or_other_themes(self):
        saved = self.library.save(self.draft())
        (self.root / 'themes' / saved.id / 'theme.json').write_text('{broken')
        settings_store.replace({'active_theme': saved.id, 'theme_migration_version': 1})
        self.assertEqual(self.library.startup(settings_store.load()).id, 'builtin:default')
        self.assertEqual(len(self.library.list_themes()), 8)
        self.assertTrue(self.library.issues)
        self.assertTrue((self.root / 'themes' / saved.id / 'theme.json').exists())

    def test_rename_delete_and_validation_never_use_names_as_paths(self):
        saved = self.library.save(self.draft(True), '../same/name')
        renamed = self.library.rename(saved.id, '  New name  ')
        self.assertEqual(renamed.name, 'New name')
        self.library.activate(saved.id)
        self.library.delete(saved.id)
        self.assertEqual(settings_store.get('active_theme'), 'builtin:default')
        self.assertFalse((self.root / 'themes' / saved.id).exists())
        self.assertTrue(self.media.exists())
        for name in ('', ' ' * 2, 'a' * 81):
            with self.subTest(name=name), self.assertRaises(model.ThemeError):
                self.library.save(self.draft(), name)
        with self.assertRaises(model.ThemeError):
            self.library.delete('builtin:default')
        with self.assertRaises(model.ThemeError):
            self.library.load('../outside')


if __name__ == '__main__':
    unittest.main()
