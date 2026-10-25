from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import threading
import uuid
import zipfile

from features import settings_store
from features.color_themes import PRESETS, is_hex_color, resolve_colors
from features.theme_media import MAX_MEDIA_BYTES, validate_media
from features.theme_model import Background, Theme, ThemeError, builtin_theme, theme_from_dict, theme_to_dict, validate_theme
from utils.app_paths import get_data_dir
from utils.atomic_io import write_json_atomic


MAX_MANIFEST_BYTES = 256 * 1024
MAX_ARCHIVE_BYTES = 260 * 1024 * 1024
MIGRATION_SETTING = 'theme_migration_version'
MIGRATION_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, 'ram-theme:legacy-migration:v1'))
_CHUNK_BYTES = 1024 * 1024


def _safe_relative(value: str) -> bool:
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in ('', '.', '..') for part in value.split('/'))


def _stream(source, destination, limit: int) -> None:
    total = 0
    while chunk := source.read(min(_CHUNK_BYTES, limit - total + 1)):
        total += len(chunk)
        if total > limit:
            raise ThemeError('The background is too large. Choose media smaller than 250 MiB.')
        destination.write(chunk)




def _validate_media(path: Path) -> None:
    validate_media(path, max_bytes=MAX_MEDIA_BYTES)


class ThemeLibrary:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir if data_dir is not None else get_data_dir()).resolve()
        self.root = self.data_dir / 'themes'
        self.imports = self.root / '.imports'
        self.issues: list[str] = []
        self._lock = threading.RLock()

    def _issue(self, message: str) -> None:
        if message not in self.issues:
            self.issues.append(message)

    def _check_root(self) -> None:
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise ThemeError('The theme folder must be a local owned directory, not a link.')

    def _directory(self, theme_id: str) -> Path:
        try:
            valid = isinstance(theme_id, str) and str(uuid.UUID(theme_id)) == theme_id
        except (ValueError, AttributeError):
            valid = False
        if not valid:
            raise ThemeError('Choose an existing custom theme with a valid ID.')
        self._check_root()
        directory = self.root / theme_id
        if directory.is_symlink() or directory.resolve() != directory:
            raise ThemeError('The theme directory is a link and cannot be used safely.')
        return directory

    def list_themes(self) -> list[Theme]:
        with self._lock:
            result = [builtin_theme(name) for name in PRESETS]
            try:
                self._check_root()
                directories = sorted(self.root.iterdir()) if self.root.exists() else []
            except (OSError, ThemeError) as error:
                self._issue(f'The theme library could not be read: {error}')
                return result
            for directory in directories:
                if directory.name.startswith('.') or not directory.is_dir():
                    continue
                try:
                    result.append(self.load(directory.name))
                except ThemeError as error:
                    self._issue(f'Theme {directory.name} is unavailable: {error}')
            return result

    def load(self, theme_id: str) -> Theme:
        with self._lock:
            if isinstance(theme_id, str) and theme_id.startswith('builtin:'):
                return builtin_theme(theme_id[8:])
            directory = self._directory(theme_id)
            path = directory / 'theme.json'
            try:
                if path.is_symlink() or path.stat().st_size > MAX_MANIFEST_BYTES:
                    raise ThemeError('The saved theme manifest is linked or too large.')
                theme = theme_from_dict(json.loads(path.read_text(encoding='utf-8')))
                if theme.id != theme_id:
                    raise ThemeError('The theme ID does not match its folder. Keep the file for recovery.')
                if theme.background.path:
                    relative = theme.background.path
                    if not _safe_relative(relative) or len(PurePosixPath(relative).parts) != 1:
                        raise ThemeError('The saved background must reference this theme\'s own media file.')
                    media = directory / relative
                    if media.is_symlink() or media.resolve().parent != directory:
                        raise ThemeError('The saved background points outside its theme folder.')
                    theme.background.path = str(media)
                    if not media.is_file():
                        self._issue(f'Background for {theme.name} is missing. Choose another background in Themes.')
                return theme
            except ThemeError:
                raise
            except (OSError, ValueError, TypeError, UnicodeError) as error:
                raise ThemeError(f'The saved theme could not be loaded. Keep its files for recovery: {error}') from error

    def save(self, theme: Theme, name=None) -> Theme:
        with self._lock:
            return self._save(theme, name)

    def _save(self, theme: Theme, name=None, forced_id=None) -> Theme:
        draft = theme.clone()
        if name is not None:
            draft.name = name
        validate_theme(draft)
        draft.name = draft.name.strip()
        existing = False
        if draft.id and not draft.id.startswith('builtin:'):
            existing = (self._directory(draft.id) / 'theme.json').exists()
        draft.id = forced_id or (draft.id if existing else str(uuid.uuid4()))
        directory = self._directory(draft.id)
        old_path = None
        copied_path = None
        created = not directory.exists()
        try:
            if (directory / 'theme.json').exists():
                old_path = self.load(draft.id).background.path
            directory.mkdir(parents=True, exist_ok=True)
            asset = ''
            if draft.background.path:
                source = Path(draft.background.path)
                _validate_media(source)
                if old_path and os.path.normcase(str(source.resolve())) == os.path.normcase(str(Path(old_path).resolve())):
                    asset = source.name
                else:
                    asset = 'background-' + str(uuid.uuid4()) + source.suffix.lower()
                    copied_path = directory / asset
                    with source.open('rb') as incoming, copied_path.open('xb') as outgoing:
                        _stream(incoming, outgoing, MAX_MEDIA_BYTES)
                    _validate_media(copied_path)
            elif draft.background.enabled:
                raise ThemeError('Choose a background file or turn off the background before saving.')
            document = theme_to_dict(draft)
            document['background']['path'] = asset
            write_json_atomic(str(directory / 'theme.json'), document, prefix='.theme.', fsync=True)
        except (OSError, ValueError, TypeError) as error:
            if copied_path is not None:
                try:
                    copied_path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    self._issue(f'An interrupted background copy could not be removed: {cleanup_error}')
            if created:
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if isinstance(error, ThemeError):
                raise
            raise ThemeError(f'The theme could not be saved. Check folder access and free disk space: {error}') from error
        draft.background.path = str(directory / asset) if asset else ''
        draft._staging_dir = ''
        # Remove old owned media after the replacement document is durable
        try:
            for child in directory.iterdir():
                if child.name.startswith('background-') and child.name != asset and (child.is_file() or child.is_symlink()):
                    child.unlink()
        except OSError as error:
            self._issue(f'Unused backgrounds could not be removed: {error}')
        return draft

    def activate(self, theme_id: str) -> None:
        with self._lock:
            self.load(theme_id)
            try:
                settings_store.save('active_theme', theme_id)
            except OSError as error:
                raise ThemeError(f'The active theme could not be saved. Check settings folder access: {error}') from error

    def rename(self, theme_id: str, name: str) -> Theme:
        with self._lock:
            self._directory(theme_id)
            theme = self.load(theme_id)
            return self._save(theme, name)

    def delete(self, theme_id: str) -> None:
        with self._lock:
            directory = self._directory(theme_id)
            self.load(theme_id)
            if settings_store.get('active_theme') == theme_id:
                self.activate('builtin:default')
            try:
                shutil.rmtree(directory)
            except OSError as error:
                raise ThemeError(f'The theme could not be deleted. Close programs using its files: {error}') from error

    def export_theme(self, theme: Theme, path) -> None:
        validate_theme(theme)
        destination = Path(path)
        temporary = None
        try:
            document = theme_to_dict(theme)
            document.pop('id', None)
            document.pop('recovery', None)
            media = Path(theme.background.path) if theme.background.path else None
            if media:
                _validate_media(media)
                document['background']['path'] = 'background' + media.suffix.lower()
            elif theme.background.enabled:
                raise ThemeError('Choose a background file or turn off the background before exporting.')
            descriptor, temporary = tempfile.mkstemp(prefix='.ramtheme-', suffix='.tmp', dir=destination.parent)
            os.close(descriptor)
            manifest = json.dumps(document, ensure_ascii=False).encode('utf-8')
            if len(manifest) > MAX_MANIFEST_BYTES:
                raise ThemeError('The theme manifest is too large to export.')
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, allowZip64=False) as archive:
                archive.writestr('theme.json', manifest)
                if media:
                    with media.open('rb') as source, archive.open(document['background']['path'], 'w') as target:
                        _stream(source, target, MAX_MEDIA_BYTES)
            if os.path.getsize(temporary) > MAX_ARCHIVE_BYTES:
                raise ThemeError('The theme package is too large to export.')
            os.replace(temporary, destination)
            temporary = None
        except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
            if isinstance(error, ThemeError):
                raise
            raise ThemeError(f'The theme could not be exported. Check the destination and free disk space: {error}') from error
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def import_theme(self, path) -> Theme:
        staging = None
        try:
            if Path(path).stat().st_size > MAX_ARCHIVE_BYTES:
                raise ThemeError('The theme archive is too large. The limit is 260 MiB.')
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                if len(entries) > 2 or len(set(names)) != len(names) or names.count('theme.json') != 1:
                    raise ThemeError('A theme package must contain one theme.json and at most one background.')
                for entry in entries:
                    file_type = stat.S_IFMT(entry.external_attr >> 16)
                    if (entry.orig_filename != entry.filename or not _safe_relative(entry.orig_filename) or
                            entry.is_dir() or entry.flag_bits & 1 or
                            file_type not in (0, stat.S_IFREG)):
                        raise ThemeError('The theme archive contains unsafe paths, links, or encrypted entries.')
                    limit = MAX_MANIFEST_BYTES if entry.filename == 'theme.json' else MAX_MEDIA_BYTES
                    if entry.file_size > limit or entry.compress_size > MAX_ARCHIVE_BYTES:
                        raise ThemeError('The theme package contains an oversized file.')
                with archive.open('theme.json') as source:
                    raw = source.read(MAX_MANIFEST_BYTES + 1)
                if len(raw) > MAX_MANIFEST_BYTES:
                    raise ThemeError('The theme manifest is too large.')
                document = json.loads(raw.decode('utf-8'))
                if not isinstance(document, dict):
                    raise ThemeError('The package manifest must be a theme document.')
                document['id'] = ''
                document.pop('recovery', None)
                theme = theme_from_dict(document)
                asset = theme.background.path
                if asset and (not _safe_relative(asset) or asset == 'theme.json' or asset not in names):
                    raise ThemeError('The packaged background is missing or has an unsafe path.')
                if set(names) != ({'theme.json', asset} if asset else {'theme.json'}):
                    raise ThemeError('The theme package contains an unexpected file.')
                if not asset and theme.background.enabled:
                    raise ThemeError('The theme enables a background without including its media.')
                with self._lock:
                    self._check_root()
                    if self.imports.is_symlink() or self.imports.resolve() != self.imports:
                        raise ThemeError('The import staging folder must not be a link.')
                    staging = self.imports / str(uuid.uuid4())
                    staging.mkdir(parents=True)
                if asset:
                    target = staging / ('background' + PurePosixPath(asset).suffix.lower())
                    with archive.open(asset) as source, target.open('xb') as output:
                        _stream(source, output, MAX_MEDIA_BYTES)
                    _validate_media(target)
                    theme.background.path = str(target)
                theme._staging_dir = str(staging)
                return theme
        except (OSError, ValueError, TypeError, UnicodeError, RuntimeError, NotImplementedError,
                zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as error:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            if isinstance(error, ThemeError):
                raise
            raise ThemeError(f'The theme package could not be imported. Choose a valid .ramtheme file: {error}') from error

    def discard_import(self, theme: Theme) -> None:
        with self._lock:
            if not theme._staging_dir:
                return
            staging = Path(theme._staging_dir)
            if (staging.parent != self.imports or staging.is_symlink() or
                    staging.resolve().parent != self.imports.resolve()):
                raise ThemeError('The import staging path is invalid and was not removed.')
            try:
                uuid.UUID(staging.name)
                shutil.rmtree(staging, ignore_errors=False)
            except FileNotFoundError:
                pass
            except (ValueError, OSError) as error:
                raise ThemeError(f'The imported background could not be cleaned up: {error}') from error
            theme._staging_dir = ''

    def startup(self, settings: dict) -> Theme:
        with self._lock:
            settings = settings if isinstance(settings, dict) else {}
            if settings.get(MIGRATION_SETTING) != 1:
                try:
                    return self._migrate(settings)
                except (OSError, ThemeError) as error:
                    self._issue(f'Previous appearance migration could not finish and will retry: {error}')
            active = settings_store.get('active_theme', settings.get('active_theme', 'builtin:default'))
            try:
                return self.load(active)
            except ThemeError as error:
                self._issue(f'The selected theme is unavailable; Default is active: {error}')
                try:
                    self.activate('builtin:default')
                except ThemeError as save_error:
                    self._issue(str(save_error))
                return builtin_theme('default')

    def _migrate(self, settings: dict) -> Theme:
        migration_file = self._directory(MIGRATION_ID) / 'theme.json'
        if migration_file.exists():
            theme = self.load(MIGRATION_ID)
        else:
            name = settings.get('color_theme')
            preset = name if isinstance(name, str) and name in PRESETS else 'default'
            theme = builtin_theme(preset)
            accent = settings.get('accent_color')
            custom_accent = is_hex_color(accent) and accent.upper() != theme.colors['ACCENT']
            legacy = settings.get('custom_background')
            legacy = legacy if isinstance(legacy, dict) else {}
            enabled = bool(legacy.get('enabled', False))
            if custom_accent or enabled:
                theme.id = ''
                theme.name = 'My previous theme'
                theme.colors = resolve_colors(settings)
                if enabled:
                    for old, role, default in (('text', 'TEXT', '#EDEDED'), ('muted', 'MUTED', '#AAAAAA'),
                                                ('outline', 'LINE', '#242424')):
                        value = legacy.get(old, default)
                        theme.colors[role] = value.upper() if is_hex_color(value) else default
                    try:
                        blur = max(0, min(100, int(legacy.get('blur', 50))))
                    except (ValueError, TypeError, OverflowError):
                        blur = 50
                    tint = legacy.get('tint', '#181818')
                    tint = tint.upper() if is_hex_color(tint) else '#181818'
                    source = str(legacy.get('path', '') or '')
                    theme.background = Background(True, source, blur, round(blur * 160 / 255), tint)
                    try:
                        _validate_media(Path(source))
                    except (OSError, ValueError) as error:
                        theme.recovery['legacy_background_path'] = source
                        theme.background.enabled = False
                        theme.background.path = ''
                        self._issue(f'Previous background could not be copied. Its colors were preserved: {error}')
                theme.starting_colors = theme.colors.copy()
                theme = self._save(theme, forced_id=MIGRATION_ID)
        self.activate(theme.id)
        try:
            settings_store.save(MIGRATION_SETTING, 1)
        except OSError as error:
            self._issue(f'Appearance migration will finish on the next launch: {error}')
        return theme
