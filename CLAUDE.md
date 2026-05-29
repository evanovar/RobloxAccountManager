# CLAUDE.md — Roblox Account Manager

## Project overview

Python/Tkinter desktop application for managing multiple Roblox accounts on Windows.
Handles account storage (encrypted), game launching, multi-instance Roblox, auto-rejoin
monitoring, Discord bot/webhook integration, and anti-AFK.

Run with: `py main.py`
Dependencies: `py -m pip install -r requirements.txt`
Requires: Windows, Google Chrome (or bundled Chromium), Python 3.7+

## Architecture

```
main.py                         — Entry point; encryption setup → builds UI
classes/
  __init__.py                   — Exports RobloxAccountManager
  account_manager.py            — RobloxAccountManager: account CRUD, Selenium browser
                                  automation (login flow + browser-click join)
  roblox_api.py                 — RobloxAPI: all HTTP calls (auth ticket, presence,
                                  game info, launch deep-link building, _execute_launch)
  encryption.py                 — Hardware / Password / No-op encryption for cookie storage
  discord_manager.py            — Discord webhook + bot integration
utils/
  ui.py                         — AccountManagerUI (Tkinter): entire UI + all feature logic
                                  (auto-rejoin threads, multi-Roblox, favorites, settings…)
  encryption_setup.py           — First-run encryption wizard
  theme_manager.py              — Dynamic Tk theme/color application
```

### Key responsibilities by file

| File | Owns |
|---|---|
| `roblox_api.py` | Every outbound Roblox HTTP request; `launch_roblox` builds `roblox-player:` deep-link + calls `_execute_launch`; `get_auth_ticket` POSTs to auth.roblox.com |
| `account_manager.py` | Cookie/account persistence, Selenium Chrome driver (`setup_chrome_driver`), browser-based login flow, **`launch_roblox_browser_click`**, **`launch_roblox_profile_join`** (flagged-account path), `open_authenticated_browser` (detached Chrome to any URL), `_try_click_chrome_protocol_dialog` (UI-Automation helper) |
| `utils/ui.py` | All Tkinter windows; auto-rejoin worker threads (`auto_rejoin_worker_for_account`); `_launch_and_track_pid` dispatches launches and tracks PIDs; `_detect_join_off_cycle` + `_is_account_currently_in_game` gate the profile-join path |

## Game launching — two code paths

### 1. API path (default)
`_launch_and_track_pid` → `manager.launch_roblox` → `RobloxAPI.launch_roblox`
→ `RobloxAPI.get_auth_ticket` (POST `auth.roblox.com/v1/authentication-ticket/`)
→ builds `roblox-player:1+launchmode:play+gameinfo:<ticket>+...` URL
→ `RobloxAPI._execute_launch` (os.startfile / Bloxstrap / Fishstrap / Froststrap / Voidstrap / client)

### 2. Profile-join path (flagged-account anti-captcha)
Roblox flags accounts for botting and requires a captcha on API-initiated joins
(`Roblox/WinInet` User-Agent on the auth-ticket request is detectable). The
original browser-click approach (clicking Play on the game page) still triggers
captchas for flagged accounts. The path that works: clicking **Join** on a
friend's Roblox profile inside a real browser.

`_launch_and_track_pid` (config has `join_off_username`)
→ checks parent is in-game via `_is_account_currently_in_game` (returns `None`
   if not — auto-rejoin treats `None` as "skipped, don't burn a retry")
→ `manager.launch_roblox_profile_join(account, friend_username, …)`
  1. Resolves friend username → user ID via `RobloxAPI.get_user_id_from_username`
  2. Spins up a fresh temp Chrome profile via Selenium
  3. Plants `.ROBLOSECURITY` cookie on roblox.com
  4. Navigates to `https://www.roblox.com/users/{friend_user_id}/profile`
  5. Injects the same JS interceptors as below (capture `roblox-player:` URLs)
  6. Polls up to 20 s for a "Join" button using a multi-strategy selector
     (testid → class → text/aria-label/title)
  7. Clicks via `ActionChains.move_to_element(...).click()` so the click carries
     `event.isTrusted=true` (synthetic JS `.click()` is often ignored by Roblox)
  8. Waits up to 20 s for **either** `window.__rblxLaunchUrl` to be populated
     **or** Chrome's "Open Roblox Game Client?" protocol dialog to appear
  9. URL path → `RobloxAPI._execute_launch` (honors launcher preference).
     Dialog path → `_try_click_chrome_protocol_dialog` dismisses it via
     `pywinauto` UI Automation (Chrome's dialog is canvas-drawn, not real
     Win32 controls); the OS protocol handler launches whatever client is
     registered for `roblox-player:` (launcher preference is ignored on this
     path)
  10. Cleans up driver + temp profile

### Legacy browser-click path
`launch_roblox_browser_click` (same idea, clicking Play on the game page) is
still in `account_manager.py` but no longer wired into the UI — flagged
accounts get captcha'd on this path, so it was replaced by profile-join.

**Limitations of profile-join:** the dependent account ends up in whatever
game the friend is in, not necessarily a configured `place_id`. The auto-rejoin
worker accounts for this by forcing the "in any game" presence branch whenever
`join_off_username` is set.

### Launch Roblox Home dropdown
The homepage "Launch Roblox Home  ▼" button opens a popup menu:
- **Launch in App** → `launch_home()` (existing — API-path launch with `place_id=""`)
- **Launch in Browser** → `launch_home_in_browser()` → spawns a thread per
  selected account calling `manager.open_authenticated_browser(uname,
  "https://www.roblox.com/home")` (detached Chrome, cookie planted, no driver
  cleanup — Chrome stays open after the function returns)

## Auto-rejoin system

Config stored in `settings['auto_rejoin_configs']` keyed by username:
```python
{
  'place_id': str,             # optional if join_off_username is set
  'private_server': str,       # link code, share URL, or empty
  'job_id': str,
  'check_interval': int,       # seconds between presence checks
  'max_retries': int,
  'check_presence': bool,      # forced False when join_off_username is set
  'check_internet_before_launch': bool,
  'join_off_username': str,    # if set: profile-join off this friend
                               # (mutually exclusive with place_id in the UI)
}
```

`place_id` and `join_off_username` are **mutually exclusive** at the UI layer
(Add/Edit dialogs enforce on save + live-disable the other entry as one is
typed in). Either alone is valid; both empty is rejected.

### Cycle detection + ordering
- `_detect_join_off_cycle(account, new_join_off)` runs on save; rejects configs
  that would form a cycle (A→B→A).
- Worker startup order doesn't matter. The dependent (B) calls
  `_is_account_currently_in_game(parent)` before each launch attempt; if the
  parent isn't in-game, `_launch_and_track_pid` returns `None`. Workers treat
  `None` as "skipped, retry next tick" (no max-retries penalty). When the
  parent enters a game, the next tick of the dependent's worker fires the
  profile-join.

Each active config runs `auto_rejoin_worker_for_account` in a daemon thread.
The worker uses `RobloxAPI.get_player_presence` to detect disconnection, then calls
`_launch_and_track_pid` to relaunch. PID tracking (`auto_rejoin_pids`) is used to
kill the old Roblox instance before relaunching.

## Launcher preferences

Set in settings as `roblox_launcher`. Options: `default`, `bloxstrap`, `fishstrap`,
`froststrap`, `voidstrap`, `client`, `custom`. Handled entirely in
`RobloxAPI._execute_launch` — all launch code paths end here.

## Encryption

Three modes selected at first run: Hardware (tied to machine), Password (portable),
None. Cookies are stored encrypted in `AccountManagerData/`. Switching modes is
supported via the Tool tab in Settings.

## Data folder

`AccountManagerData/` (next to the executable / working dir):
- `accounts.json` — encrypted account cookies + metadata
- `settings.json` — all UI/feature settings
- `encryption_config.json` — which encryption mode is active
- `icon.ico`, `discordlogo.png` — downloaded on first run if absent
- `Chromium/` — bundled Chromium if user downloads it via Settings → Tools

## Windows-only notes

- Uses `ctypes.windll.user32` for window detection (`FindWindowW`)
- Uses `subprocess` with `CREATE_NO_WINDOW` creationflags throughout
- Uses `tasklist` / `taskkill` for PID management in auto-rejoin
- Multi-Roblox mutex removal uses `handle64.exe` (Windows tool)
- Anti-AFK uses `win32api` / `win32con` for key/mouse injection
- Profile-join uses `pywinauto` (UIA backend) to dismiss Chrome's external-
  protocol confirmation dialog. The dialog's buttons are canvas-drawn, not
  Win32 controls, so `win32gui.EnumChildWindows` can't reach them — UIA can.
