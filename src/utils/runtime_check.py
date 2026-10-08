"""File-backed packaging check, dispatched before UI or account initialization."""

import json
from pathlib import Path


def helper_main(arguments: list[str]) -> int:
    if len(arguments) not in (1, 2):
        return 2
    try:
        # Import inside the check so a broken DLL produces a useful report even
        # in a windowed executable, where stdout and stderr are unavailable.
        import _hashlib
        import ssl
        import requests
        from urllib3.util import ssl_ as urllib3_ssl

        ssl.create_default_context()
        if urllib3_ssl.SSLContext is None:
            raise RuntimeError("urllib3 could not load SSLContext")
        _hashlib.openssl_sha256(b"runtime check").hexdigest()
        report = {"ok": True, "openssl_version": ssl.OPENSSL_VERSION}
        if len(arguments) == 2:
            if not arguments[1].startswith("https://"):
                raise ValueError("Runtime network check requires an HTTPS URL")
            with requests.get(arguments[1], timeout=15) as response:
                response.raise_for_status()
                report["https_status"] = response.status_code
    except Exception as exc:
        report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        Path(arguments[0]).write_text(json.dumps(report), encoding="utf-8")
    except OSError:
        return 1
    return 0 if report["ok"] else 1
