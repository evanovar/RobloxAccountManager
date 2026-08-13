"""
Roblox GlobalBasicSettings_13.xml loading and editing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import tempfile
import threading
import xml.etree.ElementTree as ET

from classes.operation_result import OperationResult, unexpected_result
import features.settings_store as settings_store_mod
from utils.app_paths import get_data_dir


_SETTINGS_FILENAME = "GlobalBasicSettings_13.xml"
_BACKUP_SUFFIX = ".ram.bak"
_UI_SETTINGS_FILENAME = "ui_settings.json"
_LOCAL_PROFILE_FILENAME = "RobloxSettings.json"
_SUPPORTED_TYPES = {
    "bool",
    "int",
    "int64",
    "float",
    "double",
    "token",
    "string",
    "BinaryString",
    "SharedString",
    "SecurityCapabilities",
}
_VECTOR_TYPES = {"Vector2", "Vector3"}
_BASIC_KEYS = {
    "FramerateCap",
    "MasterVolume",
    "SavedQualityLevel",
}
_WRITE_LOCK = threading.RLock()
_CACHE_LOCK = threading.RLock()
_AUTO_APPLY_CACHE: dict[str, object] = {}

try:
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
    ET.register_namespace("xmime", "http://www.w3.org/2005/05/xmlmime")
except Exception:
    pass


@dataclass(frozen=True)
class RobloxSetting:
    key: str
    name: str
    xml_type: str
    value: str
    path: tuple[int, ...]
    editable: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "xml_type": self.xml_type,
            "value": self.value,
            "path": list(self.path),
            "editable": self.editable,
        }


def get_settings_path() -> Path | None:
    local_appdata = os.getenv("LOCALAPPDATA")
    if not local_appdata:
        return None
    return Path(local_appdata) / "Roblox" / _SETTINGS_FILENAME


def _get_ui_settings_path() -> Path:
    return Path(get_data_dir()) / _UI_SETTINGS_FILENAME


def _load_ui_settings() -> dict:
    return settings_store_mod.load()


def _save_ui_settings(settings: dict) -> OperationResult:
    path = _get_ui_settings_path()
    try:
        settings_store_mod.replace(settings)
        return OperationResult.success()
    except (OSError, TypeError, ValueError) as exc:
        return OperationResult.failure(
            "ROBLOX_SETTINGS_CONFIG_WRITE_FAILED",
            "Roblox Settings Configuration Could Not Be Saved",
            "The Roblox settings configuration could not be saved.",
            detail=f"Path: {path}\n{type(exc).__name__}: {exc}",
        )


def get_local_profile_path() -> Path:
    return Path(get_data_dir()) / _LOCAL_PROFILE_FILENAME


def _save_local_profile(profile: dict) -> OperationResult:
    path = get_local_profile_path()
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{_LOCAL_PROFILE_FILENAME}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        os.close(file_descriptor)
        temp_path = Path(temp_name)
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(profile, handle, indent=2)
        os.replace(temp_path, path)
        temp_path = None
        _clear_auto_apply_cache()
        return OperationResult.success(data=profile)
    except OSError as exc:
        return OperationResult.failure(
            "ROBLOX_PROFILE_WRITE_FAILED",
            "Roblox Settings Profile Could Not Be Saved",
            "The local Roblox settings profile could not be saved.",
            detail=f"Path: {path}\n{type(exc).__name__}: {exc}",
        )
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _load_local_profile_file() -> dict | None:
    path = get_local_profile_path()
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as handle:
            profile = json.load(handle)
        if isinstance(profile, dict) and isinstance(profile.get("settings"), dict):
            return profile
    except (OSError, ValueError, TypeError):
        return None
    return None


def has_startup_customizations() -> bool:
    profile = _load_local_profile_file()
    if profile is not None:
        if bool(profile.get("advanced_auto_apply", False)):
            return True
        basic = profile.get("basic", {})
        if isinstance(basic, dict):
            return any(
                isinstance(entry, dict) and bool(entry.get("enabled", False))
                for entry in basic.values()
            )

    settings = _load_ui_settings()
    return any(bool(settings.get(key, False)) for key in (
        "roblox_settings_auto_apply",
        "framerate_cap_enabled",
        "master_volume_enabled",
        "start_quality_enabled",
    ))


def _legacy_profile_values() -> dict[str, object]:
    settings = _load_ui_settings()
    return {
        "auto_apply": bool(settings.get("roblox_settings_auto_apply", False)),
        "lock_owned": bool(settings.get("roblox_settings_lock_owned", False)),
        "managed": {
            "FramerateCap": (
                bool(settings.get("framerate_cap_enabled", False)),
                str(settings.get("framerate_cap_value", 60)),
            ),
            "MasterVolume": (
                bool(settings.get("master_volume_enabled", False)),
                str(settings.get("master_volume_value", "1.0")),
            ),
            "SavedQualityLevel": (
                bool(settings.get("start_quality_enabled", False)),
                str(settings.get("start_quality_value", 0)),
            ),
        },
    }


def _profile_from_settings(
    data: dict,
    existing: dict | None = None,
    replace_values: bool = False,
) -> dict:
    existing = existing if isinstance(existing, dict) else {}
    old_values = _legacy_profile_values()
    old_managed = old_values["managed"]
    existing_settings = existing.get("settings", {})
    if not isinstance(existing_settings, dict):
        existing_settings = {}
    existing_basic = existing.get("basic", {})
    if not isinstance(existing_basic, dict):
        existing_basic = {}
    existing_pending = existing.get("advanced_pending", {})
    if not isinstance(existing_pending, dict):
        existing_pending = {}
    existing_source = existing.get("source", {})
    if not isinstance(existing_source, dict):
        existing_source = {}
    captured_at = str(existing_source.get("captured_at", ""))
    if replace_values or not captured_at:
        captured_at = datetime.now(timezone.utc).isoformat()
    profile_settings: dict[str, dict] = {}
    basic: dict[str, dict] = {}
    for record in data.get("settings", []):
        key = str(record.get("key", ""))
        if not key:
            continue
        old_entry = existing_settings.get(key, {})
        if not isinstance(old_entry, dict):
            old_entry = {}
        source_value = str(record.get("value", ""))
        value = source_value
        pending_entry = existing_pending.get(key, {})
        if not isinstance(pending_entry, dict):
            pending_entry = {}
        basic_entry = existing_basic.get(key, {})
        if not isinstance(basic_entry, dict):
            basic_entry = {}

        if not replace_values and key in existing_settings:
            value = str(old_entry.get("value", source_value))
            if pending_entry:
                value = str(pending_entry.get("value", value))

        old_apply = bool(old_entry.get("apply", False))
        if key in _BASIC_KEYS and old_apply and key not in existing_basic:
            basic_entry = {
                "enabled": True,
                "value": str(old_entry.get("value", source_value)),
            }
        elif key in old_managed and key not in existing_basic:
            enabled, old_value = old_managed[key]
            basic_entry = {
                "enabled": bool(enabled),
                "value": str(old_value),
            }

        if key in _BASIC_KEYS:
            basic[key] = {
                "enabled": bool(basic_entry.get("enabled", False)),
                "value": str(basic_entry.get("value", source_value)),
            }
        profile_settings[key] = {
            "name": str(record.get("name", key)),
            "type": str(record.get("xml_type", "string")),
            "xml_type": str(record.get("xml_type", "string")),
            "path": list(record.get("path", [])),
            "editable": bool(record.get("editable", True)),
            "value": value,
            "source_value": source_value,
        }
    return {
        "version": 3,
        "advanced_auto_apply": bool(existing.get(
            "advanced_auto_apply",
            existing.get("auto_apply", old_values["auto_apply"]),
        )),
        "lock_owned": bool(existing.get("lock_owned", old_values["lock_owned"])),
        "source": {
            "xml_hash": str(data.get("file_hash", "")),
            "captured_at": captured_at,
        },
        "settings": profile_settings,
        "basic": basic,
    }


def _profile_display_records(profile: dict, data: dict | None = None) -> list[dict]:
    records = []
    basic = profile.get("basic", {})
    if not isinstance(basic, dict):
        basic = {}
    real_records = {
        str(record.get("key", "")): dict(record)
        for record in (data or {}).get("settings", [])
        if str(record.get("key", ""))
    }
    for key, entry in profile.get("settings", {}).items():
        record = dict(entry)
        record["key"] = key
        record["name"] = str(entry.get("name", key))
        record["xml_type"] = str(entry.get("xml_type", entry.get("type", "string")))
        basic_entry = basic.get(key, {})
        record["value"] = str(entry.get("value", ""))
        real_record = real_records.get(key, {})
        source_value = str(real_record.get(
            "value",
            entry.get("source_value", ""),
        ))
        record["source_value"] = source_value
        record["pending"] = record["value"] != source_value
        record["basic_enabled"] = bool(
            isinstance(basic_entry, dict) and basic_entry.get("enabled", False)
        )
        records.append(record)
    return records


def load_local_profile() -> OperationResult:
    with _WRITE_LOCK:
        return _load_local_profile()


def _load_local_profile() -> OperationResult:
    loaded = load_settings()
    if not loaded:
        return loaded
    data = loaded.data or {}
    existing = _load_local_profile_file()
    profile = _profile_from_settings(
        data,
        existing,
        replace_values=existing is None,
    )
    profile_changed = profile != existing
    if profile_changed:
        saved = _save_local_profile(profile)
        if not saved:
            return saved
    profile_data = dict(data)
    profile_data["profile"] = profile
    profile_data["settings"] = _profile_display_records(profile, data)
    profile_data["profile_path"] = str(get_local_profile_path())
    return OperationResult.success(data=profile_data)


def reload_local_profile_from_roblox() -> OperationResult:
    with _WRITE_LOCK:
        return _reload_local_profile_from_roblox()


def _reload_local_profile_from_roblox() -> OperationResult:
    loaded = load_settings()
    if not loaded:
        return loaded
    data = loaded.data or {}
    profile = _profile_from_settings(
        data,
        _load_local_profile_file(),
        replace_values=True,
    )
    saved = _save_local_profile(profile)
    if not saved:
        return saved
    profile_data = dict(data)
    profile_data["profile"] = profile
    profile_data["settings"] = _profile_display_records(profile, data)
    profile_data["profile_path"] = str(get_local_profile_path())
    return OperationResult.success(data=profile_data)


def save_local_profile(profile: dict) -> OperationResult:
    with _WRITE_LOCK:
        return _save_local_profile(profile)


def _load_profile_for_edit() -> tuple[dict | None, OperationResult | None]:
    profile = _load_local_profile_file()
    if profile is None:
        loaded = load_local_profile()
        if not loaded:
            return None, loaded
        profile = dict((loaded.data or {}).get("profile", {}))
    return profile, None


def save_basic_setting(
    key: str,
    value: str | None = None,
    enabled: bool | None = None,
) -> OperationResult:
    with _WRITE_LOCK:
        return _save_basic_setting(key, value=value, enabled=enabled)


def _save_basic_setting(
    key: str,
    value: str | None = None,
    enabled: bool | None = None,
) -> OperationResult:
    if key not in _BASIC_KEYS:
        return OperationResult.failure(
            "ROBLOX_BASIC_SETTING_INVALID",
            "Invalid Basic Setting",
            f"The setting '{key}' is not a supported Basic setting.",
        )
    profile, error = _load_profile_for_edit()
    if error:
        return error
    if profile is None:
        return OperationResult.failure(
            "ROBLOX_LOCAL_SETTINGS_INVALID",
            "Roblox Settings Profile Invalid",
            "The local Roblox settings profile could not be loaded.",
        )
    entry = profile.get("settings", {}).get(key)
    if not isinstance(entry, dict):
        return OperationResult.failure(
            "ROBLOX_SETTING_NOT_FOUND",
            "Roblox Setting Not Found",
            f"The setting '{key}' could not be found.",
            detail=f"Profile: {get_local_profile_path()}",
        )
    basic = profile.setdefault("basic", {})
    current = basic.get(key, {})
    if not isinstance(current, dict):
        current = {}
    if value is not None:
        validation = _validate_managed_value(key, value)
        if not validation:
            return validation
        current["value"] = str(validation.data)
    else:
        current["value"] = str(current.get("value", entry.get("value", "")))
    if enabled is not None:
        current["enabled"] = bool(enabled)
    else:
        current["enabled"] = bool(current.get("enabled", False))
    basic[key] = current
    return _save_local_profile(profile)


def save_advanced_setting(key: str, value: str) -> OperationResult:
    with _WRITE_LOCK:
        return _save_advanced_setting(key, value)


def _save_advanced_setting(key: str, value: str) -> OperationResult:
    profile, error = _load_profile_for_edit()
    if error:
        return error
    if profile is None:
        return OperationResult.failure(
            "ROBLOX_LOCAL_SETTINGS_INVALID",
            "Roblox Settings Profile Invalid",
            "The local Roblox settings profile could not be loaded.",
        )
    entry = profile.get("settings", {}).get(key)
    if not isinstance(entry, dict):
        return OperationResult.failure(
            "ROBLOX_SETTING_NOT_FOUND",
            "Roblox Setting Not Found",
            f"The setting '{key}' could not be found.",
            detail=f"Profile: {get_local_profile_path()}",
        )
    validation = _validate_managed_value(key, value) if key in {
        "FramerateCap",
        "MasterVolume",
        "SavedQualityLevel",
    } else validate_value(
        str(entry.get("xml_type", entry.get("type", "string"))),
        value,
    )
    if not validation:
        return validation
    normalized = str(validation.data)
    entry["value"] = normalized
    return _save_local_profile(profile)


def save_advanced_auto_apply(enabled: bool) -> OperationResult:
    with _WRITE_LOCK:
        profile, error = _load_profile_for_edit()
        if error:
            return error
        if profile is None:
            return OperationResult.failure(
                "ROBLOX_LOCAL_SETTINGS_INVALID",
                "Roblox Settings Profile Invalid",
                "The local Roblox settings profile could not be loaded.",
            )
        if not enabled and bool(profile.get("lock_owned", False)):
            unlock_result = unlock_framerate_cap()
            if not unlock_result:
                return unlock_result
            profile["lock_owned"] = False
        profile["advanced_auto_apply"] = bool(enabled)
        return _save_local_profile(profile)


def get_customization_config(
    settings: dict | None = None,
    records: dict[str, dict] | None = None,
) -> dict[str, object]:
    profile = _load_local_profile_file()
    current = dict(settings) if isinstance(settings, dict) else _load_ui_settings()
    if profile is None:
        managed = _legacy_profile_values()["managed"]
        return {
            "auto_apply": bool(_legacy_profile_values()["auto_apply"]),
            "framerate_enabled": bool(managed["FramerateCap"][0]),
            "framerate_value": str(managed["FramerateCap"][1]),
            "master_volume_enabled": bool(managed["MasterVolume"][0]),
            "master_volume_value": str(managed["MasterVolume"][1]),
            "start_quality_enabled": bool(managed["SavedQualityLevel"][0]),
            "start_quality_value": str(managed["SavedQualityLevel"][1]),
            "lock_owned": bool(current.get("roblox_settings_lock_owned", False)),
        }

    basic = profile.get("basic", {})
    if not isinstance(basic, dict):
        basic = {}
    profile_settings = profile.get("settings", {})
    def _entry(key: str, fallback: str) -> dict:
        value = basic.get(key, {})
        if not isinstance(value, dict):
            value = profile_settings.get(key, {})
        return value if isinstance(value, dict) else {"value": fallback, "apply": False}

    framerate = _entry("FramerateCap", "60")
    volume = _entry("MasterVolume", "1.0")
    quality = _entry("SavedQualityLevel", "0")
    return {
        "auto_apply": bool(profile.get("advanced_auto_apply", False)),
        "framerate_enabled": bool(framerate.get("enabled", False)),
        "framerate_value": str(framerate.get("value", "60")),
        "master_volume_enabled": bool(volume.get("enabled", False)),
        "master_volume_value": str(volume.get("value", "1.0")),
        "start_quality_enabled": bool(quality.get("enabled", False)),
        "start_quality_value": str(quality.get("value", "0")),
        "lock_owned": bool(profile.get("lock_owned", False)),
    }


def _validate_managed_value(key: str, value: str) -> OperationResult:
    if key == "FramerateCap":
        try:
            parsed = int(str(value).strip())
        except ValueError:
            parsed = None
        if parsed is None or parsed < -1 or parsed > 999:
            return OperationResult.failure(
                "ROBLOX_FRAMERATE_VALUE_INVALID",
                "Invalid Framerate Cap",
                "Framerate Cap must be between -1 and 999.",
                detail=f"Setting: {key}\nValue: {value}",
            )
        return OperationResult.success(data=str(parsed))

    if key == "MasterVolume":
        try:
            parsed = float(str(value).strip())
        except ValueError:
            parsed = math.nan
        if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
            return OperationResult.failure(
                "ROBLOX_MASTER_VOLUME_INVALID",
                "Invalid Master Volume",
                "Master Volume must be between 0.0 and 1.0.",
                detail=f"Setting: {key}\nValue: {value}",
            )
        return OperationResult.success(data=f"{parsed:.1f}")

    if key == "SavedQualityLevel":
        try:
            parsed = int(str(value).strip())
        except ValueError:
            parsed = None
        if parsed is None or parsed < 0 or parsed > 10:
            return OperationResult.failure(
                "ROBLOX_START_QUALITY_INVALID",
                "Invalid Start Quality",
                "Start Quality must be between 0 and 10.",
                detail=f"Setting: {key}\nValue: {value}",
            )
        return OperationResult.success(data=str(parsed))

    return OperationResult.success(data=str(value))


def _customization_signature(config: dict[str, object]) -> str:
    values = (
        bool(config.get("auto_apply", False)),
        bool(config.get("framerate_enabled", False)),
        str(config.get("framerate_value", "")),
        bool(config.get("master_volume_enabled", False)),
        str(config.get("master_volume_value", "")),
        bool(config.get("start_quality_enabled", False)),
        str(config.get("start_quality_value", "")),
    )
    return repr(values)


def _clear_auto_apply_cache() -> None:
    with _CACHE_LOCK:
        _AUTO_APPLY_CACHE.clear()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _find_properties(root: ET.Element) -> ET.Element | None:
    for item in root.iter():
        if (
            _local_name(item.tag) == "Item"
            and item.attrib.get("class") == "UserGameSettings"
        ):
            for child in list(item):
                if _local_name(child.tag) == "Properties":
                    return child
    return None


def _value_type(element: ET.Element, parent_type: str) -> str:
    tag_type = _local_name(element.tag)
    if parent_type in _VECTOR_TYPES:
        return "float"
    if tag_type in _SUPPORTED_TYPES:
        return tag_type
    return "string"


def _collect_settings(
    element: ET.Element,
    path: tuple[int, ...],
    prefix: str,
    parent_type: str = "",
) -> list[RobloxSetting]:
    settings: list[RobloxSetting] = []
    children = list(element)
    if children:
        current_type = _local_name(element.tag)
        for index, child in enumerate(children):
            child_name = child.attrib.get("name", "") or _local_name(child.tag)
            child_prefix = f"{prefix}.{child_name}" if prefix else child_name
            settings.extend(_collect_settings(
                child,
                path + (index,),
                child_prefix,
                current_type,
            ))
        return settings

    if not prefix:
        return settings

    value = element.text or ""
    settings.append(RobloxSetting(
        key=prefix,
        name=prefix,
        xml_type=_value_type(element, parent_type),
        value=value,
        path=path,
        editable=True,
    ))
    return settings


def _parse_settings(path: Path) -> tuple[ET.ElementTree, list[RobloxSetting]]:
    tree = ET.parse(path)
    properties = _find_properties(tree.getroot())
    if properties is None:
        raise LookupError("UserGameSettings Properties element was not found.")

    settings: list[RobloxSetting] = []
    seen_keys: set[str] = set()
    for index, element in enumerate(list(properties)):
        name = element.attrib.get("name", "") or _local_name(element.tag)
        records = _collect_settings(element, (index,), name)
        for record in records:
            key = record.key
            if key in seen_keys:
                key = f"{key} [{'.'.join(str(part) for part in record.path)}]"
                record = RobloxSetting(
                    key=key,
                    name=key,
                    xml_type=record.xml_type,
                    value=record.value,
                    path=record.path,
                    editable=record.editable,
                )
            seen_keys.add(key)
            settings.append(record)
    return tree, settings


def load_settings() -> OperationResult:
    path = get_settings_path()
    if path is None:
        return OperationResult.failure(
            "ROBLOX_SETTINGS_PATH_UNAVAILABLE",
            "Roblox Settings Path Unavailable",
            "The Windows Local AppData folder could not be found.",
        )
    if not path.is_file():
        return OperationResult.failure(
            "ROBLOX_SETTINGS_NOT_FOUND",
            "Roblox Settings Not Found",
            "Launch Roblox once to create the settings file.",
            detail=f"Expected path: {path}",
        )

    try:
        file_hash = _file_hash(path)
        _, settings = _parse_settings(path)
        return OperationResult.success(data={
            "path": str(path),
            "file_hash": file_hash,
            "settings": [setting.as_dict() for setting in settings],
            "read_only": not bool(os.stat(path).st_mode & stat.S_IWRITE),
        })
    except ET.ParseError as exc:
        return OperationResult.failure(
            "ROBLOX_SETTINGS_XML_INVALID",
            "Roblox Settings XML Invalid",
            "The Roblox settings file contains invalid XML.",
            detail=f"Path: {path}\n{exc}",
        )
    except LookupError as exc:
        return OperationResult.failure(
            "ROBLOX_SETTINGS_PROPERTIES_MISSING",
            "Roblox Settings Properties Missing",
            "The UserGameSettings properties could not be found.",
            detail=f"Path: {path}\n{exc}",
        )
    except OSError as exc:
        return OperationResult.failure(
            "ROBLOX_SETTINGS_READ_FAILED",
            "Roblox Settings Could Not Be Read",
            "The Roblox settings file could not be read.",
            detail=f"Path: {path}\n{type(exc).__name__}: {exc}",
        )
    except Exception as exc:
        return unexpected_result("Loading Roblox settings", exc)


def validate_value(xml_type: str, value: str) -> OperationResult:
    text = str(value)
    if xml_type == "bool":
        if text.strip().lower() not in {"true", "false"}:
            return OperationResult.failure(
                "ROBLOX_SETTINGS_VALUE_INVALID",
                "Invalid Roblox Setting Value",
                "Boolean values must be true or false.",
                detail=f"Type: {xml_type}\nValue: {text}",
            )
        return OperationResult.success(data=text.strip().lower())

    if xml_type in {"int", "int64", "token"}:
        try:
            parsed = int(text.strip())
        except ValueError:
            return OperationResult.failure(
                "ROBLOX_SETTINGS_VALUE_INVALID",
                "Invalid Roblox Setting Value",
                "This setting requires a whole number.",
                detail=f"Type: {xml_type}\nValue: {text}",
            )
        return OperationResult.success(data=str(parsed))

    if xml_type in {"float", "double"}:
        try:
            parsed = float(text.strip())
        except ValueError:
            parsed = math.nan
        if not math.isfinite(parsed):
            return OperationResult.failure(
                "ROBLOX_SETTINGS_VALUE_INVALID",
                "Invalid Roblox Setting Value",
                "This setting requires a finite decimal number.",
                detail=f"Type: {xml_type}\nValue: {text}",
            )
        return OperationResult.success(data=text.strip())

    return OperationResult.success(data=text)


def _resolve_path(root: ET.Element, path: tuple[int, ...]) -> ET.Element | None:
    current = root
    for index in path:
        children = list(current)
        if index < 0 or index >= len(children):
            return None
        current = children[index]
    return current


def _set_writable(path: Path) -> None:
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


def _set_read_only(path: Path, read_only: bool) -> None:
    os.chmod(path, stat.S_IREAD if read_only else stat.S_IREAD | stat.S_IWRITE)


def _restore_backup(path: Path, backup_path: Path, original_read_only: bool) -> None:
    if backup_path.is_file():
        _set_writable(path)
        shutil.copy2(backup_path, path)
    _set_read_only(path, original_read_only)


def apply_settings(
    changes: dict[str, str],
    expected_hash: str = "",
    framerate_locked: bool | None = None,
) -> OperationResult:
    path = get_settings_path()
    if path is None:
        return OperationResult.failure(
            "ROBLOX_SETTINGS_PATH_UNAVAILABLE",
            "Roblox Settings Path Unavailable",
            "The Windows Local AppData folder could not be found.",
        )
    if not path.is_file():
        return OperationResult.failure(
            "ROBLOX_SETTINGS_NOT_FOUND",
            "Roblox Settings Not Found",
            "Launch Roblox once to create the settings file.",
            detail=f"Expected path: {path}",
        )

    with _WRITE_LOCK:
        backup_path = Path(str(path) + _BACKUP_SUFFIX)
        temp_path: Path | None = None
        original_read_only = False
        replaced = False
        try:
            current_hash = _file_hash(path)
            if expected_hash and current_hash != expected_hash:
                return OperationResult.failure(
                    "ROBLOX_SETTINGS_CHANGED",
                    "Roblox Settings Changed",
                    "Roblox changed the settings file after it was loaded. Reload it before applying changes.",
                    detail=f"Path: {path}",
                )

            tree, settings = _parse_settings(path)
            properties = _find_properties(tree.getroot())
            if properties is None:
                return OperationResult.failure(
                    "ROBLOX_SETTINGS_PROPERTIES_MISSING",
                    "Roblox Settings Properties Missing",
                    "The UserGameSettings properties could not be found.",
                    detail=f"Path: {path}",
                )

            by_key = {setting.key: setting for setting in settings}
            normalized_changes: dict[str, str] = {}
            for key, value in changes.items():
                setting = by_key.get(key)
                if setting is None:
                    return OperationResult.failure(
                        "ROBLOX_SETTING_NOT_FOUND",
                        "Roblox Setting Not Found",
                        f"The setting '{key}' could not be found.",
                        detail=f"Path: {path}",
                    )
                validation = validate_value(setting.xml_type, value)
                if not validation:
                    return validation
                normalized_changes[key] = validation.data

            original_read_only = not bool(os.stat(path).st_mode & stat.S_IWRITE)
            if normalized_changes:
                try:
                    shutil.copy2(path, backup_path)
                except OSError as exc:
                    return OperationResult.failure(
                        "ROBLOX_SETTINGS_BACKUP_FAILED",
                        "Roblox Settings Backup Failed",
                        "A backup of the Roblox settings file could not be created.",
                        detail=f"Path: {path}\n{type(exc).__name__}: {exc}",
                    )
                _set_writable(path)
                for key, value in normalized_changes.items():
                    element = _resolve_path(properties, tuple(by_key[key].path))
                    if element is None:
                        raise LookupError(f"Setting path disappeared: {key}")
                    element.text = value

                file_descriptor, temp_name = tempfile.mkstemp(
                    prefix=f".{_SETTINGS_FILENAME}.",
                    suffix=".tmp",
                    dir=str(path.parent),
                )
                os.close(file_descriptor)
                temp_path = Path(temp_name)
                tree.write(temp_path, encoding="utf-8", xml_declaration=False)
                ET.parse(temp_path)
                os.replace(temp_path, path)
                temp_path = None
                replaced = True

            if framerate_locked is None:
                target_read_only = original_read_only
            else:
                target_read_only = bool(framerate_locked)
            _set_read_only(path, target_read_only)

            loaded = load_settings()
            if not loaded:
                raise RuntimeError(
                    f"Written settings could not be loaded: {loaded.code}"
                )
            _clear_auto_apply_cache()
            return OperationResult.success(
                "Roblox settings applied successfully.",
                data=loaded.data,
            )
        except shutil.Error as exc:
            if replaced and backup_path.is_file():
                _restore_backup(path, backup_path, original_read_only)
            return OperationResult.failure(
                "ROBLOX_SETTINGS_BACKUP_FAILED",
                "Roblox Settings Backup Failed",
                "A backup of the Roblox settings file could not be created.",
                detail=f"Path: {path}\n{exc}",
            )
        except ET.ParseError as exc:
            if replaced and backup_path.is_file():
                _restore_backup(path, backup_path, original_read_only)
            return OperationResult.failure(
                "ROBLOX_SETTINGS_XML_INVALID",
                "Roblox Settings XML Invalid",
                "The updated Roblox settings file did not contain valid XML.",
                detail=f"Path: {path}\n{exc}",
            )
        except PermissionError as exc:
            if replaced and backup_path.is_file():
                _restore_backup(path, backup_path, original_read_only)
            return OperationResult.failure(
                "ROBLOX_SETTINGS_ATTRIBUTE_FAILED",
                "Roblox Settings File Is Locked",
                "Windows did not allow the Roblox settings file to be changed.",
                detail=f"Path: {path}\n{exc}",
            )
        except OSError as exc:
            if replaced and backup_path.is_file():
                _restore_backup(path, backup_path, original_read_only)
            return OperationResult.failure(
                "ROBLOX_SETTINGS_WRITE_FAILED",
                "Roblox Settings Could Not Be Written",
                "The Roblox settings file could not be updated.",
                detail=f"Path: {path}\n{type(exc).__name__}: {exc}",
            )
        except Exception as exc:
            if replaced and backup_path.is_file():
                try:
                    _restore_backup(path, backup_path, original_read_only)
                except Exception as restore_exc:
                    print(f"[ERROR] Failed to restore Roblox settings backup: {restore_exc}")
            return unexpected_result("Applying Roblox settings", exc)
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass


def load_local_profile_async(on_done) -> None:
    threading.Thread(
        target=lambda: on_done(load_local_profile()),
        daemon=True,
        name="roblox-settings-profile-load",
    ).start()


def reload_local_profile_from_roblox_async(on_done) -> None:
    threading.Thread(
        target=lambda: on_done(reload_local_profile_from_roblox()),
        daemon=True,
        name="roblox-settings-profile-reload",
    ).start()


def apply_local_profile_async(on_done) -> None:
    threading.Thread(
        target=lambda: on_done(apply_local_profile()),
        daemon=True,
        name="roblox-settings-profile-apply",
    ).start()


def apply_saved_customizations(
    settings: dict | None = None,
) -> OperationResult:
    with _WRITE_LOCK:
        loaded_profile = load_local_profile()
        if not loaded_profile:
            return loaded_profile
        profile = dict((loaded_profile.data or {}).get("profile", {}))
        advanced_auto_apply = bool(profile.get("advanced_auto_apply", False))
        return _apply_profile(
            profile,
            include_advanced=advanced_auto_apply,
            lock_advanced=advanced_auto_apply,
            use_cache=True,
        )


def _build_profile_changes(
    entries: dict,
    xml_records: dict[str, dict],
) -> OperationResult:
    changes: dict[str, str] = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict) or not bool(entry.get("editable", True)):
            continue
        record = xml_records.get(key)
        if record is None:
            continue
        value = str(entry.get("value", ""))
        validation = _validate_managed_value(key, value) if key in _BASIC_KEYS else validate_value(
            str(record.get("xml_type", entry.get("type", "string"))),
            value,
        )
        if not validation:
            return validation
        if str(record.get("value", "")) != str(validation.data):
            changes[key] = str(validation.data)
    return OperationResult.success(data=changes)


def _profile_result_data(profile: dict, data: dict) -> dict:
    display_data = dict(data)
    display_data["profile"] = profile
    display_data["settings"] = _profile_display_records(profile, data)
    display_data["profile_path"] = str(get_local_profile_path())
    return display_data


def _update_profile_sources(profile: dict, data: dict) -> None:
    records = {
        str(record["key"]): dict(record)
        for record in data.get("settings", [])
    }
    for key, entry in profile.get("settings", {}).items():
        record = records.get(key)
        if isinstance(entry, dict) and record is not None:
            entry["source_value"] = str(record.get("value", ""))
    profile["source"] = {
        "xml_hash": str(data.get("file_hash", "")),
        "captured_at": profile.get("source", {}).get("captured_at", ""),
    }


def _enabled_basic_entries(profile: dict) -> dict[str, dict]:
    basic = profile.get("basic", {})
    if not isinstance(basic, dict):
        return {}
    return {
        key: entry
        for key, entry in basic.items()
        if isinstance(entry, dict) and bool(entry.get("enabled", False))
    }


def _apply_profile(
    profile: dict,
    include_advanced: bool,
    lock_advanced: bool,
    use_cache: bool,
) -> OperationResult:
    loaded = load_settings()
    if not loaded:
        return loaded
    data = loaded.data or {}
    xml_records = {
        str(record["key"]): dict(record)
        for record in data.get("settings", [])
    }
    changes: dict[str, str] = {}
    if include_advanced:
        advanced_result = _build_profile_changes(
            profile.get("settings", {}),
            xml_records,
        )
        if not advanced_result:
            return advanced_result
        changes.update(dict(advanced_result.data or {}))

    enabled_basic = _enabled_basic_entries(profile)
    for key in enabled_basic:
        if key not in xml_records:
            return OperationResult.failure(
                "ROBLOX_MANAGED_SETTING_MISSING",
                "Roblox Setting Not Found",
                f"The enabled setting '{key}' was not found in the Roblox XML file.",
                detail=f"Setting: {key}",
            )
    for key, entry in enabled_basic.items():
        validation = _validate_managed_value(
            key,
            str(entry.get("value", "")),
        )
        if not validation:
            return validation
        normalized = str(validation.data)
        if include_advanced or str(xml_records[key].get("value", "")) != normalized:
            changes[key] = normalized

    current_hash = str(data.get("file_hash", ""))
    current_read_only = bool(data.get("read_only", False))
    lock_owned = bool(profile.get("lock_owned", False))
    if lock_advanced:
        target_read_only: bool | None = True
        resulting_lock_owned = lock_owned or not current_read_only
    elif lock_owned:
        target_read_only = False
        resulting_lock_owned = False
    else:
        target_read_only = None
        resulting_lock_owned = False

    signature_data = {
        "include_advanced": include_advanced,
        "lock_advanced": lock_advanced,
        "advanced": {
            key: str(entry.get("value", ""))
            for key, entry in profile.get("settings", {}).items()
            if include_advanced and isinstance(entry, dict)
        },
        "basic": {
            key: str(entry.get("value", ""))
            for key, entry in enabled_basic.items()
        },
    }
    signature = json.dumps(signature_data, sort_keys=True, separators=(",", ":"))

    if use_cache:
        with _CACHE_LOCK:
            if (
                _AUTO_APPLY_CACHE.get("signature") == signature
                and _AUTO_APPLY_CACHE.get("file_hash") == current_hash
                and _AUTO_APPLY_CACHE.get("read_only") == current_read_only
            ):
                return OperationResult.success(
                    "Roblox settings are already applied.",
                    data=_AUTO_APPLY_CACHE.get("data"),
                )

    attribute_change = (
        target_read_only is not None
        and current_read_only != target_read_only
    )
    if not changes and not attribute_change:
        result = OperationResult.success(
            "Roblox settings are already applied.",
            data=data,
        )
    else:
        result = apply_settings(
            changes,
            expected_hash=current_hash,
            framerate_locked=target_read_only,
        )
    if not result:
        return result

    result_data = result.data or data
    _update_profile_sources(profile, result_data)
    profile["lock_owned"] = resulting_lock_owned
    saved = _save_local_profile(profile)
    if not saved:
        return saved
    display_data = _profile_result_data(profile, result_data)
    if use_cache:
        with _CACHE_LOCK:
            _AUTO_APPLY_CACHE.update({
                "signature": signature,
                "file_hash": str(result_data.get("file_hash", current_hash)),
                "read_only": bool(result_data.get("read_only", current_read_only)),
                "data": display_data,
            })
    return OperationResult.success(
        "Roblox settings applied successfully.",
        data=display_data,
    )


def apply_local_profile(
    profile: dict | None = None,
    auto_apply: bool = False,
) -> OperationResult:
    with _WRITE_LOCK:
        return _apply_local_profile(profile, auto_apply=auto_apply)


def _apply_local_profile(
    profile: dict | None = None,
    auto_apply: bool = False,
) -> OperationResult:
    if profile is None:
        loaded_profile = load_local_profile()
        if not loaded_profile:
            return loaded_profile
        profile = dict((loaded_profile.data or {}).get("profile", {}))
    return _apply_profile(
        profile,
        include_advanced=True,
        lock_advanced=bool(profile.get("advanced_auto_apply", False)),
        use_cache=False,
    )


def apply_saved_customizations_async(settings: dict | None, on_done) -> None:
    threading.Thread(
        target=lambda: on_done(apply_saved_customizations()),
        daemon=True,
        name="roblox-settings-auto-apply",
    ).start()


def set_framerate_cap(fps: int) -> OperationResult:
    loaded = load_settings()
    if not loaded:
        return loaded
    return apply_settings(
        {"FramerateCap": str(fps)},
        expected_hash=loaded.data.get("file_hash", ""),
        framerate_locked=None,
    )


def unlock_framerate_cap() -> OperationResult:
    path = get_settings_path()
    if path is None:
        return OperationResult.failure(
            "ROBLOX_SETTINGS_PATH_UNAVAILABLE",
            "Roblox Settings Path Unavailable",
            "The Windows Local AppData folder could not be found.",
        )
    if not path.is_file():
        return OperationResult.success()
    try:
        _set_writable(path)
        return OperationResult.success()
    except Exception as exc:
        return OperationResult.failure(
            "ROBLOX_SETTINGS_ATTRIBUTE_FAILED",
            "Roblox Settings File Could Not Be Unlocked",
            "Windows did not allow the Roblox settings file to be made writable.",
            detail=f"Path: {path}\n{type(exc).__name__}: {exc}",
        )
