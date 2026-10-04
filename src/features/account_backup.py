"""
features/account_backup.py
Export saved accounts to a password protected file and import them again.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone

from classes.encryption import (
    EncryptedDataError,
    PasswordDecryptionError,
    PasswordEncryption,
)
from classes.operation_result import OperationResult, unexpected_result
from utils.atomic_io import write_json_atomic

BACKUP_FORMAT = "ram-accounts-backup"
BACKUP_VERSION = 1
MIN_PASSWORD_LENGTH = 8


def export_accounts(accounts: dict, path: str, password: str) -> OperationResult:
    if len(str(password or "")) < MIN_PASSWORD_LENGTH:
        return OperationResult.failure(
            "BACKUP_PASSWORD_TOO_SHORT",
            "Backup Password Too Short",
            f"Use a password with at least {MIN_PASSWORD_LENGTH} characters.",
        )
    if not accounts:
        return OperationResult.failure(
            "BACKUP_NO_ACCOUNTS",
            "Nothing To Export",
            "There are no saved accounts to export.",
        )
    try:
        encryptor = PasswordEncryption(password)
        package = encryptor.encrypt_data({
            "accounts": accounts,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        write_json_atomic(
            path,
            {
                "format": BACKUP_FORMAT,
                "version": BACKUP_VERSION,
                "salt": encryptor.get_salt_b64(),
                "data": package,
            },
            prefix=".backup.",
            fsync=True,
        )
    except OSError as exc:
        return OperationResult.failure(
            "BACKUP_WRITE_FAILED",
            "Backup Could Not Be Saved",
            "The backup file could not be written. Check the location and try again.",
            detail=f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:
        return unexpected_result("Exporting accounts", exc)
    return OperationResult.success(
        f"Exported {len(accounts)} account(s).",
        data={"count": len(accounts), "path": path},
    )


def read_backup(path: str, password: str) -> OperationResult:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as exc:
        return OperationResult.failure(
            "BACKUP_UNREADABLE",
            "Backup Could Not Be Read",
            "The file could not be opened as a backup.",
            detail=f"{type(exc).__name__}: {exc}",
        )

    if (
        not isinstance(document, dict)
        or document.get("format") != BACKUP_FORMAT
        or not isinstance(document.get("salt"), str)
        or not isinstance(document.get("data"), dict)
    ):
        return OperationResult.failure(
            "BACKUP_FORMAT_INVALID",
            "Not A Backup File",
            "This file is not an account backup made by this application.",
        )
    if document.get("version") != BACKUP_VERSION:
        return OperationResult.failure(
            "BACKUP_VERSION_UNSUPPORTED",
            "Backup Version Not Supported",
            "This backup was made by a different version of the application.",
            detail=f"Backup version: {document.get('version')}",
        )

    try:
        encryptor = PasswordEncryption(password, base64.b64decode(document["salt"], validate=True))
        payload = encryptor.decrypt_data(document["data"])
    except PasswordDecryptionError:
        return OperationResult.failure(
            "BACKUP_PASSWORD_INVALID",
            "Wrong Backup Password",
            "The password did not unlock this backup.",
        )
    except (EncryptedDataError, binascii.Error, ValueError) as exc:
        return OperationResult.failure(
            "BACKUP_MALFORMED",
            "Backup Is Damaged",
            "The backup file is damaged and could not be decoded.",
            detail=f"{type(exc).__name__}: {exc}",
        )

    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, dict):
        return OperationResult.failure(
            "BACKUP_MALFORMED",
            "Backup Is Damaged",
            "The backup does not contain an account list.",
        )
    valid = {
        str(name): record
        for name, record in accounts.items()
        if isinstance(record, dict) and isinstance(record.get("cookie"), str) and record["cookie"].strip()
    }
    return OperationResult.success(
        data={"accounts": valid, "skipped": len(accounts) - len(valid)},
    )


def merge_accounts(existing: dict, imported: dict, overwrite: bool) -> tuple[dict, int, int, int]:
    merged = dict(existing)
    added = updated = skipped = 0
    for name, record in imported.items():
        if name not in merged:
            merged[name] = record
            added += 1
        elif overwrite:
            merged[name] = record
            updated += 1
        else:
            skipped += 1
    return merged, added, updated, skipped


def import_accounts(manager, path: str, password: str, overwrite: bool = False) -> OperationResult:
    result = read_backup(path, password)
    if not result:
        return result
    imported = result.data["accounts"]
    if not imported:
        return OperationResult.failure(
            "BACKUP_NO_ACCOUNTS",
            "Nothing To Import",
            "The backup does not contain any usable accounts.",
        )

    with manager._accounts_lock:
        previous = manager.accounts
        merged, added, updated, skipped = merge_accounts(previous, imported, overwrite)
        manager.accounts = merged
        try:
            manager._migrate_accounts(manager.accounts)
            manager.save_accounts()
        except Exception as exc:
            manager.accounts = previous
            return unexpected_result("Saving imported accounts", exc)

    return OperationResult.success(
        f"Added {added}, updated {updated}, skipped {skipped + result.data['skipped']}.",
        data={
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "invalid": result.data["skipped"],
        },
    )
