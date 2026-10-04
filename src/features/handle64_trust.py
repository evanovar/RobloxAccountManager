"""
features/handle64_trust.py
Native Authenticode verification and an administrator-only copy used to run
Handle64 without trusting PATH, the environment or any user-writable folder.
"""

from __future__ import annotations

import atexit
import contextlib
import ctypes
import hashlib
import os
import shutil
import threading
import uuid
from ctypes import wintypes

import ntsecuritycon
import pywintypes
import win32api
import win32con
import win32file
import win32security

TRUSTED_ORGANIZATION = "Microsoft Corporation"

_WTD_UI_NONE = 2
_WTD_REVOKE_NONE = 0
_WTD_CHOICE_FILE = 1
_WTD_STATEACTION_VERIFY = 1
_WTD_STATEACTION_CLOSE = 2
_WTD_REVOCATION_CHECK_NONE = 0x10
_WTD_CACHE_ONLY_URL_RETRIEVAL = 0x1000
_CERT_NAME_ATTR_TYPE = 3
_ORGANIZATION_OID = b"2.5.4.10"
_INVALID_HANDLE = ctypes.c_void_p(-1).value


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _WintrustFileInfo(ctypes.Structure):
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pcwszFilePath", wintypes.LPCWSTR),
        ("hFile", wintypes.HANDLE),
        ("pgKnownSubject", ctypes.c_void_p),
    ]


class _WintrustData(ctypes.Structure):
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pPolicyCallbackData", ctypes.c_void_p),
        ("pSIPClientData", ctypes.c_void_p),
        ("dwUIChoice", wintypes.DWORD),
        ("fdwRevocationChecks", wintypes.DWORD),
        ("dwUnionChoice", wintypes.DWORD),
        ("pFile", ctypes.POINTER(_WintrustFileInfo)),
        ("dwStateAction", wintypes.DWORD),
        ("hWVTStateData", wintypes.HANDLE),
        ("pwszURLReference", ctypes.c_void_p),
        ("dwProvFlags", wintypes.DWORD),
        ("dwUIContext", wintypes.DWORD),
        ("pSignatureSettings", ctypes.c_void_p),
    ]


class _ProviderCert(ctypes.Structure):
    _fields_ = [("cbStruct", wintypes.DWORD), ("pCert", ctypes.c_void_p)]


_GENERIC_VERIFY_V2 = _GUID(
    0x00AAC56B, 0xCD44, 0x11D0,
    (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE),
)

_libraries: dict[str, ctypes.WinDLL] = {}


def _system_library(name: str) -> ctypes.WinDLL:
    library = _libraries.get(name)
    if library is None:
        library = ctypes.WinDLL(os.path.join(win32api.GetSystemDirectory(), name), use_last_error=True)
        _libraries[name] = library
    return library


def signer_organization(handle) -> str | None:
    wintrust = _system_library("wintrust.dll")
    crypt32 = _system_library("crypt32.dll")

    wintrust.WinVerifyTrust.argtypes = [wintypes.HANDLE, ctypes.POINTER(_GUID), ctypes.c_void_p]
    wintrust.WinVerifyTrust.restype = ctypes.c_long
    wintrust.WTHelperProvDataFromStateData.argtypes = [wintypes.HANDLE]
    wintrust.WTHelperProvDataFromStateData.restype = ctypes.c_void_p
    wintrust.WTHelperGetProvSignerFromChain.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
    ]
    wintrust.WTHelperGetProvSignerFromChain.restype = ctypes.c_void_p
    wintrust.WTHelperGetProvCertFromChain.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    wintrust.WTHelperGetProvCertFromChain.restype = ctypes.POINTER(_ProviderCert)
    crypt32.CertGetNameStringW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_char_p,
        wintypes.LPWSTR, wintypes.DWORD,
    ]
    crypt32.CertGetNameStringW.restype = wintypes.DWORD

    file_info = _WintrustFileInfo(
        ctypes.sizeof(_WintrustFileInfo), win32file.GetFinalPathNameByHandle(handle, 0), int(handle), None,
    )
    data = _WintrustData()
    data.cbStruct = ctypes.sizeof(_WintrustData)
    data.dwUIChoice = _WTD_UI_NONE
    data.fdwRevocationChecks = _WTD_REVOKE_NONE
    data.dwUnionChoice = _WTD_CHOICE_FILE
    data.pFile = ctypes.pointer(file_info)
    data.dwStateAction = _WTD_STATEACTION_VERIFY
    data.dwProvFlags = _WTD_REVOCATION_CHECK_NONE | _WTD_CACHE_ONLY_URL_RETRIEVAL

    status = wintrust.WinVerifyTrust(_INVALID_HANDLE, ctypes.byref(_GENERIC_VERIFY_V2), ctypes.byref(data))
    try:
        if status != 0:
            return None
        provider = wintrust.WTHelperProvDataFromStateData(data.hWVTStateData)
        signer = wintrust.WTHelperGetProvSignerFromChain(provider, 0, False, 0) if provider else None
        certificate = wintrust.WTHelperGetProvCertFromChain(signer, 0) if signer else None
        if not certificate or not certificate.contents.pCert:
            return None
        buffer = ctypes.create_unicode_buffer(256)
        length = crypt32.CertGetNameStringW(
            certificate.contents.pCert, _CERT_NAME_ATTR_TYPE, 0, _ORGANIZATION_OID, buffer, len(buffer),
        )
        return buffer.value if length > 1 else None
    finally:
        data.dwStateAction = _WTD_STATEACTION_CLOSE
        wintrust.WinVerifyTrust(_INVALID_HANDLE, ctypes.byref(_GENERIC_VERIFY_V2), ctypes.byref(data))


def is_trusted_signature(handle) -> bool:
    try:
        return signer_organization(handle) == TRUSTED_ORGANIZATION
    except (OSError, ValueError, pywintypes.error):
        return False


class Handle64VerificationError(RuntimeError):
    pass


_READ_CHUNK = 1024 * 1024
_FILE_NAME = "handle64.exe"
_SYSTEM_SID = "S-1-5-18"
_ADMINISTRATORS_SID = "S-1-5-32-544"

_copies: dict[str, str] = {}
_directories: list[str] = []
_state_lock = threading.Lock()


@contextlib.contextmanager
def open_locked(path: str):
    # No write or delete sharing: while this handle is open nobody can change
    # or replace the file it points at.
    try:
        handle = win32file.CreateFile(
            path,
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ,
            None,
            win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        )
    except pywintypes.error as exc:
        raise Handle64VerificationError(f"{path} could not be locked for verification: {exc.strerror}") from exc
    try:
        yield handle
    finally:
        handle.Close()


def read_all(handle) -> bytes:
    chunks = []
    while True:
        _error, chunk = win32file.ReadFile(handle, _READ_CHUNK)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def get_protected_root() -> str:
    # Only administrators can change the Windows folder, so unlike ProgramData
    # nobody else can pre-plant a junction in the path leading to the copy.
    return os.path.join(win32api.GetWindowsDirectory(), "Temp")


def create_protected_directory(root: str, extra_sids: tuple[str, ...] = ()) -> str:
    path = os.path.join(root, f"ram-h64-{uuid.uuid4().hex}")
    inherit = win32security.CONTAINER_INHERIT_ACE | win32security.OBJECT_INHERIT_ACE
    dacl = win32security.ACL()
    for sid in (_SYSTEM_SID, _ADMINISTRATORS_SID, *extra_sids):
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION_DS,
            inherit,
            ntsecuritycon.FILE_ALL_ACCESS,
            win32security.ConvertStringSidToSid(sid),
        )
    descriptor = win32security.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorDacl(True, dacl, False)
    descriptor.SetSecurityDescriptorControl(
        win32security.SE_DACL_PROTECTED, win32security.SE_DACL_PROTECTED,
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    try:
        win32file.CreateDirectory(path, attributes)
    except pywintypes.error as exc:
        raise Handle64VerificationError(
            f"A protected folder could not be created in {root}: {exc.strerror}"
        ) from exc
    return path


def _write_new_file(directory: str, data: bytes) -> str:
    path = os.path.join(directory, _FILE_NAME)
    try:
        handle = win32file.CreateFile(
            path, win32con.GENERIC_WRITE, 0, None, win32con.CREATE_NEW,
            win32con.FILE_ATTRIBUTE_NORMAL, None,
        )
    except pywintypes.error as exc:
        raise Handle64VerificationError(f"The protected copy could not be created: {exc.strerror}") from exc
    try:
        win32file.WriteFile(handle, data)
    finally:
        handle.Close()
    return path


def is_signed_by_microsoft(path: str) -> bool:
    try:
        with open_locked(path) as handle:
            return is_trusted_signature(handle)
    except Handle64VerificationError:
        return False


def trusted_executable(
    source: str,
    root: str | None = None,
    extra_sids: tuple[str, ...] = (),
) -> str:
    with open_locked(source) as handle:
        data = read_all(handle)
        digest = hashlib.sha256(data).hexdigest()
        with _state_lock:
            existing = _copies.get(digest)
        if existing and os.path.isfile(existing):
            return existing
        if not is_trusted_signature(handle):
            raise Handle64VerificationError(f"{source} is not signed by {TRUSTED_ORGANIZATION}.")

    directory = create_protected_directory(root or get_protected_root(), extra_sids)
    try:
        executable = _write_new_file(directory, data)
        with open_locked(executable) as copy:
            if hashlib.sha256(read_all(copy)).hexdigest() != digest or not is_trusted_signature(copy):
                raise Handle64VerificationError("The protected copy did not match the verified file.")
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    with _state_lock:
        _copies[digest] = executable
        _directories.append(directory)
    return executable


def release_trusted_copies() -> None:
    with _state_lock:
        directories = list(_directories)
        _directories.clear()
        _copies.clear()
    for directory in directories:
        shutil.rmtree(directory, ignore_errors=True)


atexit.register(release_trusted_copies)
