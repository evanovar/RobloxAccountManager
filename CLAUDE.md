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
| `account_manager.py` | Cookie/account persistence, Selenium Chrome driver (`setup_chrome_driver`), browser-based login flow, **`launch_roblox_browser_click`** |
| `utils/ui.py` | All Tkinter windows; auto-rejoin worker threads (`auto_rejoin_worker_for_account`); `_launch_and_track_pid` dispatches launches and tracks PIDs |

## Game launching — two code paths

### 1. API path (default)
`_launch_and_track_pid` → `manager.launch_roblox` → `RobloxAPI.launch_roblox`
→ `RobloxAPI.get_auth_ticket` (POST `auth.roblox.com/v1/authentication-ticket/`)
→ builds `roblox-player:1+launchmode:play+gameinfo:<ticket>+...` URL
→ `RobloxAPI._execute_launch` (os.startfile / Bloxstrap / Fishstrap / Froststrap / Voidstrap / client)

### 2. Browser-click path (anti-captcha)
Roblox flags accounts for botting and requires a captcha on API-initiated joins
(`Roblox/WinInet` User-Agent on the auth-ticket request is detectable).
Clicking Play inside a real browser makes the same API call with genuine browser
headers — no captcha.

`_launch_and_track_pid` (join_method == 'browser_click')
→ `manager.launch_roblox_browser_click`
  1. Spins up a fresh temp Chrome profile via Selenium
  2. Plants `.ROBLOSECURITY` cookie on roblox.com
  3. Navigates to `https://www.roblox.com/games/{place_id}[?privateServerLinkCode=…]`
  4. Injects JS interceptors for `window.open`, `iframe.src`, and anchor clicks
     so the `roblox-player:` URL is captured before Chrome shows its protocol dialog
  5. Clicks the Play button via JS (`button` text === 'Play' or aria-label)
  6. Waits up to 15 s for `window.__rblxLaunchUrl` to be populated
  7. Passes captured URL to `RobloxAPI._execute_launch` (respects launcher preference)
  8. Cleans up driver + temp profile

**Limitations of browser-click mode:** job ID targeting is not supported (the web
Play button always joins any available server). Private server link codes work fine.

## Auto-rejoin system

Config stored in `settings['auto_rejoin_configs']` keyed by username:
```python
{
  'place_id': str,
  'private_server': str,       # link code, share URL, or empty
  'job_id': str,
  'check_interval': int,       # seconds between presence checks
  'max_retries': int,
  'check_presence': bool,      # use Presence API to verify player is in target place
  'check_internet_before_launch': bool,
  'join_method': 'api' | 'browser_click',  # defaults to 'api' if absent
}
```

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
