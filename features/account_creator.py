"""
features/account_creator.py
Generate Roblox signup details and open account creation browsers.
"""

from __future__ import annotations

from datetime import datetime
import json
from queue import Empty, Queue
import re
import secrets
import string
import threading
from typing import Callable

from classes.operation_result import OperationResult, ensure_result
from features.account_actions import get_browser_result

MAX_CREATOR_BROWSERS = 5
MAX_CREATOR_ACCOUNTS = 100
MAX_USERNAME_LENGTH = 20
MAX_PREFIX_LENGTH = 14
RANDOM_SUFFIX_LENGTH = 6
_SIGNUP_URL = "https://www.roblox.com/CreateAccount"
_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
_ADJECTIVES = (
    "Bright", "Calm", "Clever", "Cool", "Cosmic", "Happy", "Jolly",
    "Kind", "Lucky", "Mellow", "Mighty", "Neon", "Quick", "Silent",
    "Solar", "Swift", "Tiny", "Urban", "Wild", "Wise",
)
_NOUNS = (
    "Badger", "Beacon", "Comet", "Falcon", "Forest", "Fox", "Galaxy",
    "Harbor", "Koala", "Maple", "Meteor", "Otter", "Panda", "Pixel",
    "Raven", "River", "Robin", "Tiger", "Voyager", "Wolf",
)


def _random_string(length: int) -> str:
    characters = string.ascii_letters + string.digits
    return "".join(secrets.choice(characters) for _ in range(max(1, length)))


def is_valid_prefix(value: str) -> bool:
    prefix = str(value or "")
    return bool(
        prefix
        and len(prefix) <= MAX_PREFIX_LENGTH
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_]*", prefix)
    )


def _generate_username(options: dict | None = None) -> str:
    settings = options or {}
    if settings.get("enable_custom_prefix"):
        prefix = str(settings.get("prefix", "") or "").strip()
        if not is_valid_prefix(prefix):
            raise ValueError("The custom prefix does not meet the requirements.")
        suffix = _random_string(RANDOM_SUFFIX_LENGTH)
        return f"{prefix}{suffix}"[:MAX_USERNAME_LENGTH]

    base = f"{secrets.choice(_ADJECTIVES)}{secrets.choice(_NOUNS)}"
    base_length = MAX_USERNAME_LENGTH - RANDOM_SUFFIX_LENGTH
    return f"{base[:base_length]}{_random_string(RANDOM_SUFFIX_LENGTH)}"[
        :MAX_USERNAME_LENGTH
    ]


def _generate_password(length: int = 18) -> str:
    characters = string.ascii_letters + string.digits + "!@#$%"
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    required.extend(secrets.choice(characters) for _ in range(length - 4))
    secrets.SystemRandom().shuffle(required)
    return "".join(required)


def _generate_signup_profile(options: dict | None = None) -> dict:
    settings = options or {}
    current_year = datetime.now().year
    year = current_year - (secrets.randbelow(27) + 19)
    candidates = []
    while len(candidates) < 10:
        username = _generate_username(settings)
        if username.lower() not in {candidate.lower() for candidate in candidates}:
            candidates.append(username)
    custom_password = str(settings.get("password", "") or "")
    return {
        "month": secrets.choice(_MONTHS),
        "day": f"{secrets.randbelow(28) + 1:02d}",
        "year": str(year),
        "usernames": candidates,
        "password": custom_password or _generate_password(),
    }


def _build_signup_script(profile: dict) -> str:
    month = json.dumps(profile["month"])
    day = json.dumps(profile["day"])
    year = json.dumps(profile["year"])
    usernames = json.dumps(profile["usernames"])
    password = json.dumps(profile["password"])

    return f"""
    (function() {{
        var usernames = {usernames};
        var password = {password};
        var usernameIndex = 0;
        var submitted = false;

        function reactChange(element) {{
            for (var key in element) {{
                if (key.indexOf('reactProps') !== -1) {{
                    var props = element[key];
                    if (props && props.onChange) {{
                        props.onChange({{ target: element }});
                    }}
                }}
            }}
        }}

        function setInput(element, value) {{
            var descriptor = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype,
                'value'
            );
            if (descriptor && descriptor.set) {{
                descriptor.set.call(element, value);
            }} else {{
                element.value = value;
            }}
            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
            reactChange(element);
        }}

        function setSelect(element, value) {{
            element.value = value;
            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
            reactChange(element);
        }}

        function chooseUsername() {{
            var usernameInput = document.getElementById('signup-username');
            if (!usernameInput || usernameIndex >= usernames.length) {{
                return false;
            }}
            setInput(usernameInput, usernames[usernameIndex]);
            usernameIndex += 1;
            return true;
        }}

        function getUsernameWarning() {{
            var warning = document.getElementById(
                'signup-usernameInputValidation'
            );
            return warning
                ? (warning.textContent || '').trim().toLowerCase()
                : '';
        }}

        function usernameRejected(warningText) {{
            return (
                warningText.indexOf('not appropriate') !== -1
                || warningText.indexOf('already in use') !== -1
            );
        }}

        function checkAfterSubmit() {{
            var warningText = getUsernameWarning();
            if (usernameRejected(warningText) && usernameIndex < usernames.length) {{
                submitted = false;
                chooseUsername();
                setTimeout(function() {{ checkUsername(40); }}, 900);
            }}
        }}

        function checkUsername(attemptsLeft) {{
            if (submitted) {{
                return;
            }}

            var signupButton = document.getElementById('signup-button');
            var warningText = getUsernameWarning();
            var rejected = usernameRejected(warningText);

            if (rejected && usernameIndex < usernames.length) {{
                chooseUsername();
                setTimeout(function() {{ checkUsername(40); }}, 900);
                return;
            }}

            if (!warningText && signupButton && !signupButton.disabled) {{
                submitted = true;
                signupButton.click();
                setTimeout(checkAfterSubmit, 1500);
                return;
            }}

            if (attemptsLeft > 0) {{
                setTimeout(
                    function() {{ checkUsername(attemptsLeft - 1); }},
                    250
                );
            }}
        }}

        function fillSignup(attemptsLeft) {{
            var monthInput = document.getElementById('MonthDropdown');
            var dayInput = document.getElementById('DayDropdown');
            var yearInput = document.getElementById('YearDropdown');
            var maleButton = document.getElementById('MaleButton');
            var usernameInput = document.getElementById('signup-username');
            var passwordInput = document.getElementById('signup-password');
            var signupButton = document.getElementById('signup-button');

            if (
                monthInput && dayInput && yearInput && maleButton
                && usernameInput && passwordInput && signupButton
            ) {{
                setSelect(monthInput, {month});
                setSelect(dayInput, {day});
                setSelect(yearInput, {year});
                if (
                    !maleButton.firstElementChild
                    || !maleButton.firstElementChild.classList.contains(
                        'gender-selected'
                    )
                ) {{
                    maleButton.click();
                }}
                chooseUsername();
                setInput(passwordInput, password);
                sessionStorage.setItem('_ram_pw', password);
                setTimeout(function() {{ checkUsername(40); }}, 900);
                return;
            }}

            if (attemptsLeft > 0) {{
                setTimeout(
                    function() {{ fillSignup(attemptsLeft - 1); }},
                    250
                );
            }}
        }}

        fillSignup(60);
    }})();
    """


def create_accounts(
    manager,
    amount: int,
    options: dict | None = None,
    on_done: Callable[[bool, str], None] = lambda *_: None,
) -> None:
    try:
        requested_amount = int(amount)
    except (TypeError, ValueError):
        on_done(False, "Account amount must be a number.")
        return

    if requested_amount < 1 or requested_amount > MAX_CREATOR_ACCOUNTS:
        on_done(
            False,
            f"Account amount must be between 1 and {MAX_CREATOR_ACCOUNTS}.",
        )
        return

    settings = dict(options or {})
    if settings.get("enable_custom_prefix"):
        prefix = str(settings.get("prefix", "") or "").strip()
        if not is_valid_prefix(prefix):
            on_done(
                False,
                "The custom prefix must only contain letters, numbers, and _. "
                "It cannot start with _.",
            )
            return
        settings["prefix"] = prefix

    custom_password = str(settings.get("password", "") or "")
    if custom_password and len(custom_password) < 8:
        on_done(False, "A custom password must contain at least 8 characters.")
        return
    settings["password"] = custom_password

    browser_result = get_browser_result()
    if not browser_result:
        on_done(
            False,
            f"{browser_result.message}\n\nError code: {browser_result.code}",
        )
        return
    browser = browser_result.data.get("browser")

    def _worker():
        profiles = [
            _generate_signup_profile(settings)
            for _ in range(requested_amount)
        ]
        existing_before = set(manager.accounts.keys())

        try:
            worker_count = min(MAX_CREATOR_BROWSERS, requested_amount)
            pending_profiles = Queue()
            failure_results: list[OperationResult] = []
            failure_lock = threading.Lock()
            for index, profile in enumerate(profiles):
                pending_profiles.put((index, profile))

            def _browser_slot(slot_index: int):
                while True:
                    try:
                        index, profile = pending_profiles.get_nowait()
                    except Empty:
                        return

                    try:
                        print(
                            f"[Account Creator] Slot {slot_index + 1} starting "
                            f"account {index + 1}/{requested_amount}."
                        )
                        result = ensure_result(manager.add_account(
                            amount=1,
                            website=_SIGNUP_URL,
                            javascript_list=[_build_signup_script(profile)],
                            password_list=[profile["password"]],
                            browser=browser,
                            window_slot=slot_index,
                            window_slot_count=worker_count,
                        ))
                        if not result:
                            with failure_lock:
                                failure_results.append(result)
                    except Exception as e:
                        print(f"[Account Creator] Browser slot failed: {e}")
                    finally:
                        pending_profiles.task_done()

            slot_threads = [
                threading.Thread(
                    target=_browser_slot,
                    args=(slot_index,),
                    daemon=True,
                    name=f"account-creator-slot-{slot_index + 1}",
                )
                for slot_index in range(worker_count)
            ]
            for slot_thread in slot_threads:
                slot_thread.start()
            for slot_thread in slot_threads:
                slot_thread.join()

            new_names = sorted(set(manager.accounts.keys()) - existing_before)
            if new_names:
                name_preview = ", ".join(new_names[:10])
                if len(new_names) > 10:
                    name_preview += f", and {len(new_names) - 10} more"
                summary = (
                    f"Created {len(new_names)}/{requested_amount} account(s). "
                    + name_preview
                )
                on_done(True, summary)
            else:
                if failure_results:
                    first_failure = failure_results[0]
                    on_done(
                        False,
                        f"{first_failure.message}\n\n"
                        f"Error code: {first_failure.code}",
                    )
                else:
                    on_done(
                        False,
                        "No accounts were created. Complete any CAPTCHA shown "
                        "in the browser and try again if the signup timed out.",
                    )
        except Exception as e:
            print(f"[Account Creator] Failed: {e}")
            on_done(False, str(e))

    threading.Thread(
        target=_worker,
        daemon=True,
        name="account-creator",
    ).start()
