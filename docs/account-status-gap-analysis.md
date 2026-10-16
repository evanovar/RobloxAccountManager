# Account status dot: gap analysis

Baseline analysis of `main` at `749d0a8`. The sections below describe the original gaps; accepted requirements and the resulting implementation are recorded at the end.

## Assessment

The feature fits the current Qt account list and available Windows/process dependencies. Rendering the indicator is small work. Reliable status collection is the main gap: the existing activity monitor detects matched local processes, but does not determine whether they are on Home, joining, connected, disconnected, or running in the tray.

The feature can remain observational and preserve launch, Auto-Rejoin, Anti-AFK, and window-management behavior. Copying their existing internal statuses directly would create misleading colors.

## Requirements and existing coverage

| Requested behavior | Existing support | Gap |
| --- | --- | --- |
| No dot when no process is running | Local process enumeration and an account activity snapshot exist. | A missing snapshot entry can also mean identification failed, monitoring is disabled, or the first scan has not completed. These are not proof of no process. |
| Light blue for Home | Home launches are distinguished from game launches at launch time. | No continuous Home detector exists. A Home launch may later join a game, and a game client may return Home. Launch intent is not current state. |
| Green for an active game, with or without PlaceID/JobID | The API wrapper exposes `in_game` separately from optional IDs; launch monitoring checks initial join evidence. | Neither establishes ongoing local connection state. The status feature needs join/leave/disconnect/teleport handling; process survival, CPU use, or an old join marker cannot establish a current connection. |
| Yellow for a non-headless process whose window was closed | Windows can be enumerated by PID, including hidden windows. | No current classifier distinguishes the user-facing client window from helper windows or tracks tray transitions. A hidden or absent window alone does not establish that the user closed it or that Roblox is in the tray. |
| Hollow dot for headless | Headless Manager tracks explicitly hidden PIDs. | The state is not included in the main account snapshot. Anti-AFK temporarily removes PIDs from that set. The set is keyed only by PID. |
| Minimal dot at the left of each account | There is already an approximately 8 px green dot over the avatar's lower-right corner. | Move/replace that indicator with one left-side slot and support fill/outline styling. Preserve space when absent so rows do not shift. |
| Live updates | Activity Monitor scans every 5 seconds; Headless Manager defaults to 10 seconds, configurable from 3 to 60. | Specify acceptable latency. Headless changes can update immediately, while process/window/game evidence uses a background scan. Combining these workers' results needs freshness rules. |

Source: [activity scanner](../src/features/presence.py), [main list and monitor UI](../src/utils/ui.py), [launch records](../src/classes/account_manager.py), [launch confirmation](../src/features/launch_monitor.py), [API wrapper](../src/classes/roblox_api.py), [Headless Manager](../src/features/headless_manager.py).

## Conflicts and behavior risks

### 1. Existing green dot and monitoring setting

The current green dot means a local process was matched to the account, including Home or a surviving background client. It is controlled indirectly by the optional Account Activity Monitor (`presence_indicator`), which also supplies RAM and CPU metrics. Disabling that monitor clears the dot's state.

The user's screenshot shows no dot beside the active `0xCA5E` account. Read-only inspection found `presence_indicator: false` in both the repository-root and `dist` data folders' `ui_settings.json` files. That explains the absence if the running app uses either folder; its actual data directory was not independently established. Existing source support must not be confused with an indicator currently visible in the user's app.

Adding a second independent dot would duplicate indicators with different meanings. Reuse the existing dot location/state integration, moving it to the requested left-side position. Decide whether the new status dots remain behind the existing monitor setting or run independently of optional metrics. Always-on dots require collection even when that setting is off.

### 2. Account identity differs across existing features

`PresenceScanner` and Headless Manager identify processes using `_get_user_id_from_pid`: the earliest unused log with a user ID within 60 seconds after process creation. Closely spaced launches can have multiple plausible matches. Cached resolutions do not reserve their log in subsequent scans' `used_logs` sets. A process without a readable matching user-ID log is omitted, including potentially a Home client.

Window Renamer already uses stronger evidence: recorded launch tracker IDs, unique tracker/log matches, bounded open-log probes, conservative timestamp fallback, and `(PID, creation time)` identity. Its resolver is private and coupled to the optional renamer; the status feature should not require enabling window renaming. Reuse the relevant evidence rules through a narrow read-only interface or focused shared helper, without redesigning all monitors.

Treat unresolved identity as unknown; do not assign another account's dot by guesswork. A recorded launch associates intended identity with a process, while authenticated log evidence can verify it. Preserve that distinction.

### 3. Auto-Rejoin uses different definitions

`AutoRejoinWorker._is_in_game` is a recovery-policy decision, not a UI game-state classifier:

- With joined-game checking disabled, any nonzero API presence can return `in_game`, including online/Home.
- With joined-game checking enabled, another place or a known different target JobID can return `disconnected` despite the account still playing.
- Unavailable API responses are already kept separate from confirmed disconnects.

Do not derive dot colors from Auto-Rejoin labels or feed dot colors into its recovery logic. An account can correctly show green while Auto-Rejoin decides it must return to the configured server.

Source: [Auto-Rejoin](../src/features/auto_rejoin.py).

### 4. Headless intent versus temporary visibility

Headless here means hiding an ordinary Roblox window; it is not a separate renderer-free client. Enabling Headless Manager does not automatically make every process headless: each PID is hidden or shown individually.

Anti-AFK calls `pause_hidden`, shows/maximizes a hidden window, sends input, and restores headless state. `pause_hidden` actually removes the PID from `_hidden_pids`. Reading either visibility or `is_hidden()` alone can therefore make a hollow dot briefly become solid or yellow. Preserve headless intent across this temporary suspension.

The headless set and identity caches use PID alone, unlike the activity scanner's creation-time-aware cache. PID reuse between scans could associate a new process with old state. Any status association needs the process creation time as well as PID.

Source: [headless state](../src/features/headless_manager.py), [Anti-AFK state capture and restoration](../src/features/account_actions.py).

### 5. Window titles are not a stable identity signal

Window Renamer can set the title to an account username or its note. Headless Manager currently accepts only `Roblox` or the username when hiding/showing/enforcing a window. A note-renamed window can therefore be marked hidden in its internal set even though the title filter prevented the hide operation.

This is a pre-existing interaction, not caused by a dot. The feature would expose it: hollow could claim a hide that did not occur. Identify candidate client windows by process identity and window characteristics rather than relying on title text. Keep any broader headless/title repair separately scoped unless needed to meet the chosen indicator contract.

### 6. Yellow overlaps green and does not prove tray residence

The requested mapping mixes connection state with presentation state. A non-headless client can have no displayed main window while game connection evidence still says connected. Decide which color wins. Recommended interpretation of the yellow requirement: yellow takes precedence for a stable background-only non-headless process, while a tooltip can retain known game information.

Minimized windows, windows covered by another app, and windows on another desktop must not automatically turn yellow. `IsWindowVisible` reports the window's visibility style, not whether the user can currently see it ([Microsoft documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-iswindowvisible)). Inspect main-window existence, visibility style, minimized state, and transition history together. Allow startup and window-recreation grace periods.

The repository contains no direct Roblox tray-state detector. Until tested against the installed client, label yellow as “running in background; no displayed client window,” rather than promising confirmed tray membership. Validate whether tray transitions retain the same process or create another one.

Yellow explicitly excludes headless, so a hollow yellow dot has no defined meaning under the requested rules. Headless Home would be hollow blue; headless in-game would be hollow green.

### 7. Network presence is account-wide

`get_player_presence` requests a user ID, not a local PID. It cannot by itself establish that a particular local process is playing; a surviving local Home process and activity on another device could produce a false green. It also introduces authenticated requests into a monitor currently documented as local-only and API-free.

Prefer evidence attached to the identified local client. A continuous local log reader is a candidate, but the required Home, connected, leave, disconnect, and teleport markers must first be validated against real current logs. Existing parsers read identity/startup information, not a complete ongoing connection state machine. Log rotation, truncation, and missing evidence need to invalidate stale conclusions. If API presence is used as supporting evidence, keep missing PlaceID/JobID separate from not-in-game, and preserve unavailable as unknown.

### 8. One account can have multiple processes

The existing activity snapshot deliberately aggregates multiple PIDs per account. A single dot needs a deterministic aggregation rule. Suggested rule: classify each process first, then prefer an active game over Home over background-only. Draw an outline only when all contributing live clients for that account are intentionally headless. Show mixed states and process counts in a tooltip.

This is a proposal: the user has not yet specified whether the most recently launched client should instead be authoritative. One dot cannot fully express simultaneous mixed states.

### 9. Unknown and transitional states are unspecified

The mapping has no truthful result for joining/loading, an open disconnect dialog, unreadable logs, unresolved identity, or a failed scan. Blue cannot safely mean “anything other than confirmed game,” since that would incorrectly assert Home. No dot cannot simultaneously guarantee no process and represent monitoring unavailable.

Before implementation, choose an explicit fallback. A neutral gray indicator with a short tooltip would preserve the requested meanings of blue, green, yellow, and no dot. If exactly the requested colors must be used, the fallback semantics need to be relaxed explicitly. A failed scan must not look like a successful empty scan, and stale green must expire.

## Smallest complete implementation boundary

1. Resolve live local process identities without depending on the rename toggle, using existing stronger evidence where available.
2. Extend the account snapshot with process identity, client state, headless intent, and evidence freshness; retain existing RAM/CPU aggregation.
3. Detect client main-window state through read-only Windows calls. Track headless suspension without changing Anti-AFK's input behavior.
4. Add validated ongoing local game/Home evidence. Keep optional IDs as metadata, never prerequisites for green.
5. Aggregate per-process states and update the existing dot through Qt signals, without rebuilding rows on each scan. Reapply the cached status on search, group, reorder, refresh, and theme changes.
6. Keep this observational: no launches, closes, hide/show calls, or Auto-Rejoin policy changes as a consequence of indicator state.

The existing dependencies support process discovery, Windows inspection, and Qt rendering. No dependency, CI, build, or storage-format changes are presently justified. Continuous game-state detection remains a feasibility checkpoint until live logs are examined.

## Verification and remaining validation

Existing focused checks passed: **94 tests** across `test_window_renamer`, `test_launch_monitor`, `test_auto_rejoin`, `test_import_and_headless_settings`, and `test_import_and_headless_controls`.

Command: `.venv/Scripts/python.exe scripts/run_tests.py --test test_window_renamer test_launch_monitor test_auto_rejoin test_import_and_headless_settings test_import_and_headless_controls`.

The first run hit sandbox access errors in the default temporary directory. Re-running with `TEMP` and `TMP` pointed to the repository's existing `tmp` directory passed. No test or application code was changed.

These checks validate relevant existing behavior; they do not validate the proposed feature. No live Roblox client transitions were exercised. Before implementation is considered complete, cover:

- Process absent, startup, Home, join success with no PlaceID/JobID, teleport, leave to Home, disconnect dialog, and process exit.
- Close to tray, restore from tray, minimize, window recreation, and temporary detection failures.
- Headless Home/game, explicit hide/show, Anti-AFK suspension/restoration, disabling Headless Manager, and PID reuse.
- Fast multi-account launches, missing/ambiguous logs, multiple processes for one account, external launches, and manager restart with clients already running.
- Window titles set to usernames or notes; monitor enabled/disabled; search, groups, drag reorder, selection, theme contrast, and display scaling.

Most important product decisions: monitoring toggle behavior, unknown/transitional display, yellow-versus-green precedence, and multiple-process aggregation. Most important technical validation: reliable current local connection/Home evidence and actual tray process/window behavior.

## Accepted requirements and implementation

The user confirmed these decisions after reviewing the analysis:

- Move the dot into a fixed slot left of the avatar. Dots and RAM/CPU remain controlled together by Account Activity Monitor.
- Light blue covers the signed-in desktop app generally, including Home, Discover, Avatar, and Settings, while outside a game.
- Green means a game connection was established, with no PlaceID/JobID requirement. Joining, teleporting, disconnect errors, sign-out, and uncertain evidence are grey.
- A stable non-headless background-only client is yellow even if its log still reports a connection. A minimized client keeps its Home/game color.
- Aggregate multiple clients in the order game, desktop, unknown, background. Outline the dot only if all matched clients are intentionally headless. Explain each state and mixed clients in tooltips.
- Target approximately two-second observations and immediate outline updates on explicit hide/show actions. Preserve the outline while Anti-AFK temporarily shows a headless window.

`features/account_status.py` now tails local client logs incrementally, matches processes using launch trackers or the existing bounded open-log helper, and keeps bindings scoped to PID plus creation time. It does not use timestamp-only account guesses or query network presence. Local current logs contained desktop-stage, sign-in, connection, disconnect, and teleport events; [Bloxstrap's activity watcher](https://github.com/bloxstraplabs/bloxstrap/blob/main/Bloxstrap/Integrations/ActivityWatcher.cs) provides a primary implementation reference for several connection markers. Roblox may change these markers, so missing evidence remains unknown.

Initial identity discovery runs separately from the normal status scan and can take longer than two seconds. If unidentified local Roblox processes could belong to an otherwise unmatched saved account, that account shows grey with an identity explanation and no attributed RAM/CPU. Failed observations invalidate old status instead of claiming an empty process list. Known headless clients use a separate intent identity while Anti-AFK suspends enforcement. Headless window selection also accepts note-renamed top-level client windows.

Launch confirmation and Auto-Rejoin recovery policies are unchanged. The README and setting tooltip describe the new behavior. Unit and Qt tests cover state transitions, missing IDs, log replacement and failures, process identity ambiguity/reuse, aggregation, headless suspension, layout, tooltips, settings, and stale updates after monitor toggles. Live tray and UI transitions still require manual testing; historical log replay and read-only process inspection do not replace that testing.
