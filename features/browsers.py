"""
Browser selection and executable resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil

from classes.operation_result import OperationResult
import features.chromium as chromium_mod


@dataclass(frozen=True)
class BrowserDescriptor:
    key: str
    label: str
    driver_type: str
    executable_path: str
    driver_path: str = ""
    bundled: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "driver_type": self.driver_type,
            "executable_path": self.executable_path,
            "driver_path": self.driver_path,
            "bundled": self.bundled,
        }


SUPPORTED_BROWSERS = (
    ("chrome", "Google Chrome"),
    ("firefox", "Mozilla Firefox"),
    ("edge", "Microsoft Edge"),
    ("chromium", "Chromium"),
)


def _standard_paths(browser_type: str) -> list[str]:
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    local_appdata = os.environ.get("LOCALAPPDATA", "")

    if browser_type == "chrome":
        relative = os.path.join("Google", "Chrome", "Application", "chrome.exe")
        candidates = [
            os.path.join(program_files, relative),
            os.path.join(program_files_x86, relative),
            os.path.join(local_appdata, relative),
        ]
        path_names = ("chrome.exe", "chrome")
    elif browser_type == "firefox":
        relative = os.path.join("Mozilla Firefox", "firefox.exe")
        candidates = [
            os.path.join(program_files, relative),
            os.path.join(program_files_x86, relative),
        ]
        path_names = ("firefox.exe", "firefox")
    elif browser_type == "edge":
        relative = os.path.join("Microsoft", "Edge", "Application", "msedge.exe")
        candidates = [
            os.path.join(program_files_x86, relative),
            os.path.join(program_files, relative),
            os.path.join(local_appdata, relative),
        ]
        path_names = ("msedge.exe", "msedge")
    else:
        return []

    for name in path_names:
        path_candidate = shutil.which(name)
        if path_candidate:
            candidates.append(path_candidate)

    return list(dict.fromkeys(path for path in candidates if path))


def _missing_result(browser_type: str, checked_paths: list[str]) -> OperationResult:
    labels = dict(SUPPORTED_BROWSERS)
    key = browser_type.upper()
    label = labels.get(browser_type, "Selected browser")
    return OperationResult.failure(
        f"{key}_NOT_INSTALLED" if browser_type in labels else "BROWSER_SELECTION_INVALID",
        f"{label} Not Found" if browser_type in labels else "Invalid Browser Selection",
        (
            f"{label} could not be found. Select another browser or use the built-in "
            "Chromium under Settings -> Misc."
            if browser_type in labels
            else "Select Chrome, Firefox, Edge, or Chromium in Browser Engine settings."
        ),
        detail=(
            "No registry or default-browser lookup was used. Checked paths:\n"
            + "\n".join(checked_paths)
        ),
    )


def resolve_browser(browser_type: str) -> OperationResult:
    selected = str(browser_type or "chrome").strip().lower()
    labels = dict(SUPPORTED_BROWSERS)
    if selected not in labels:
        return _missing_result(selected, [])

    if selected == "chromium":
        validation = chromium_mod.validate_chromium()
        if not validation:
            return validation
        return OperationResult.success(data={
            "browser": BrowserDescriptor(
                key="chromium",
                label="Chromium",
                driver_type="chrome",
                executable_path=validation.data.get("browser_path", ""),
                driver_path=validation.data.get("driver_path", ""),
                bundled=True,
            ).as_dict(),
        })

    checked_paths = _standard_paths(selected)
    for candidate in checked_paths:
        if os.path.isfile(candidate):
            driver_type = "firefox" if selected == "firefox" else selected
            return OperationResult.success(data={
                "browser": BrowserDescriptor(
                    key=selected,
                    label=labels[selected],
                    driver_type=driver_type,
                    executable_path=candidate,
                ).as_dict(),
            })

    return _missing_result(selected, checked_paths)
