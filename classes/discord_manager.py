"""
Discord Manager
Handles webhook and bot integrations for the program.
"""

import asyncio
import io
import threading
import requests
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

class DiscordManager:
    COLOR_ERROR = 0xE74C3C
    COLOR_SUCCESS = 0x2ECC71
    COLOR_INFO = 0x3498DB
    COLOR_WARNING = 0xF39C12
    COLOR_REJOIN = 0xEB459E
    COLOR_ANTAFK = 0x1ABC9C
    COLOR_DEFAULT = 0x5865F2

    _COLOR_PRIORITY = [0xE74C3C, 0xF39C12, 0xEB459E, 0x1ABC9C, 0x2ECC71, 0x3498DB, 0x5865F2]
    _BATCH_DELAY = 2.0
    _MAX_LINES = 20
    _WEBHOOK = "webhook"
    _BOT = "bot"

    def __init__(self, settings: dict, app=None):
        self.settings = settings
        self.app = app

        self._batch_lock = threading.Lock()
        self._batch_items = {self._WEBHOOK: [], self._BOT: []}
        self._batch_timers = {self._WEBHOOK: None, self._BOT: None}

        self._bot_lock = threading.Lock()
        self._bot_thread = None
        self._bot_loop = None
        self._bot = None
        self._bot_token_in_use = None

        self.refresh()

    def set_app(self, app):
        self.app = app
        self.refresh()

    def _cfg(self, mode=None) -> dict:
        if mode == self._BOT:
            return self.settings.setdefault("discord_bot", {})
        if mode == self._WEBHOOK:
            return self.settings.setdefault("discord_webhook", {})

        active_mode = self.active_mode
        if active_mode == self._BOT:
            return self.settings.setdefault("discord_bot", {})
        return self.settings.setdefault("discord_webhook", {})

    @property
    def webhook_cfg(self) -> dict:
        return self._cfg(self._WEBHOOK)

    @property
    def bot_cfg(self) -> dict:
        return self._cfg(self._BOT)

    @property
    def ui_mode(self) -> str:
        return self.settings.get("discord_ui_mode", self._WEBHOOK)

    @property
    def webhook_enabled(self) -> bool:
        return self.webhook_cfg.get("enabled", False)

    @property
    def webhook_url(self) -> str:
        return self.webhook_cfg.get("url", "").strip()

    @property
    def bot_enabled(self) -> bool:
        return self.bot_cfg.get("enabled", False)

    @property
    def bot_token(self) -> str:
        if self.app and hasattr(self.app, "get_discord_bot_token"):
            try:
                token = self.app.get_discord_bot_token()
                if token:
                    return str(token).strip()
            except Exception:
                pass
        return self.bot_cfg.get("token", "").strip()

    @property
    def bot_channel_id(self):
        value = self.bot_cfg.get("channel_id")
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    @property
    def active_mode(self) -> str:
        if self.bot_enabled:
            return self._BOT
        if self.webhook_enabled:
            return self._WEBHOOK
        return self.ui_mode

    @property
    def enabled(self) -> bool:
        return self.webhook_enabled or self.bot_enabled

    @property
    def url(self) -> str:
        if self.active_mode == self._BOT:
            return self.bot_token
        return self.webhook_url

    @property
    def screenshot_enabled(self) -> bool:
        return self._cfg().get("screenshot_enabled", False)

    @property
    def screenshot_interval_minutes(self) -> int:
        try:
            return max(1, int(self._cfg().get("screenshot_interval_minutes", 60)))
        except (TypeError, ValueError):
            return 60

    def has_active_target(self) -> bool:
        return self._has_mode_target(self.active_mode)

    def _has_mode_target(self, mode: str) -> bool:
        cfg = self._cfg(mode)
        if not cfg.get("enabled", False):
            return False
        if mode == self._WEBHOOK:
            return bool(cfg.get("url", "").strip())
        return bool(self.bot_token) and bool(cfg.get("channel_id"))

    def refresh(self):
        if self.bot_enabled and self.bot_token:
            self._start_bot()
        else:
            self._stop_bot()

        if self.bot_enabled and not self.bot_token:
            self._stop_bot()

    def shutdown(self):
        self._stop_bot()

    def send_embed(self, title: str, description: str, color: int, fields: list = None, ping_user_id: str = None):
        if self.webhook_enabled and self.webhook_url:
            self._send_webhook_embed(self.webhook_url, title, description, color, fields=fields, ping_user_id=ping_user_id)

        if self.bot_enabled and self.bot_token and self.bot_channel_id:
            self._send_bot_embed(title, description, color, fields=fields, ping_user_id=ping_user_id)

    def send_rejoin_embed(self, title: str, description: str, color: int, fields: list = None, ping_user_id: str = None):
        for mode in (self._WEBHOOK, self._BOT):
            cfg = self._cfg(mode)
            if not cfg.get("enabled", False):
                continue
            if not cfg.get("log_auto_rejoin", True):
                continue
            if mode == self._WEBHOOK and self.webhook_url:
                self._send_webhook_embed(self.webhook_url, title, description, color, fields=fields, ping_user_id=ping_user_id)
            elif mode == self._BOT and self.bot_token and self.bot_channel_id:
                self._send_bot_embed(title, description, color, fields=fields, ping_user_id=ping_user_id)

    def send_screenshot(self, image_bytes: bytes, caption: str = ""):
        if not image_bytes:
            return

        if self.webhook_enabled and self.webhook_url:
            self._send_webhook_screenshot(self.webhook_url, image_bytes, caption)

        if self.bot_enabled and self.bot_token and self.bot_channel_id:
            self._send_bot_file(image_bytes, "screenshot.png", caption or "Screenshot")

    def log_message(self, message: str):
        msg = message.strip()
        if not msg:
            return

        if "[Anti-AFK]" in msg and "[ERROR]" not in msg:
            return

        for mode in (self._WEBHOOK, self._BOT):
            cfg = self._cfg(mode)
            if not self._is_mode_enabled(mode, cfg):
                continue
            if not self._passes_keyword_filter(msg):
                continue
            if not self._should_send_log(cfg, msg):
                continue

            is_error = "[ERROR]" in msg
            is_success = "[SUCCESS]" in msg
            is_info = "[INFO]" in msg
            is_warning = "[WARNING]" in msg
            is_rejoin = "[Auto-Rejoin]" in msg

            if is_error:
                color = self.COLOR_ERROR
            elif is_success:
                color = self.COLOR_SUCCESS
            elif is_warning:
                color = self.COLOR_WARNING
            elif is_rejoin:
                color = self.COLOR_REJOIN
            elif is_info:
                color = self.COLOR_INFO
            else:
                color = self.COLOR_DEFAULT

            ping_user_id = None
            if cfg.get("enable_ping") and cfg.get("ping_user_id", "").strip():
                if is_error and cfg.get("ping_on_error", True):
                    ping_user_id = cfg.get("ping_user_id", "").strip()

            with self._batch_lock:
                self._batch_items[mode].append((color, msg, ping_user_id))
                timer = self._batch_timers[mode]
                if timer is None or not timer.is_alive():
                    timer = threading.Timer(self._BATCH_DELAY, self._flush_batch, args=(mode,))
                    timer.daemon = True
                    timer.start()
                    self._batch_timers[mode] = timer

    def _passes_keyword_filter(self, msg: str) -> bool:
        if "[ERROR]" in msg:
            return True

        msg_lower = msg.lower()
        for pattern in self.settings.get("console_filters", []):
            if pattern and pattern.lower() in msg_lower:
                return False
        return True

    def _should_send_log(self, cfg: dict, msg: str) -> bool:
        log_all = cfg.get("log_everything", False)
        log_errors = cfg.get("log_errors", True)
        log_success = cfg.get("log_success", True)
        log_info = cfg.get("log_info", False)
        log_warnings = cfg.get("log_warnings", True)
        log_rejoin_console = cfg.get("log_auto_rejoin_console", False)

        is_error = "[ERROR]" in msg
        is_success = "[SUCCESS]" in msg
        is_info = "[INFO]" in msg
        is_warning = "[WARNING]" in msg
        is_rejoin = "[Auto-Rejoin]" in msg

        if log_all:
            return True
        if is_error and log_errors:
            return True
        if is_success and log_success:
            return True
        if is_info and log_info:
            return True
        if is_warning and log_warnings:
            return True
        if is_rejoin and log_rejoin_console:
            return True
        return False

    def _is_mode_enabled(self, mode: str, cfg: dict) -> bool:
        if not cfg.get("enabled", False):
            return False
        if mode == self._WEBHOOK:
            return bool(cfg.get("url", "").strip())
        return bool(self.bot_token) and bool(self.bot_channel_id)

    def _flush_batch(self, mode: str):
        with self._batch_lock:
            items = self._batch_items[mode]
            if not items:
                self._batch_timers[mode] = None
                return
            current = items[:self._MAX_LINES]
            self._batch_items[mode] = items[self._MAX_LINES:]
            has_more = bool(self._batch_items[mode])

        colors_in_batch = {color for (color, _, _) in current}
        color = self.COLOR_DEFAULT
        for value in self._COLOR_PRIORITY:
            if value in colors_in_batch:
                color = value
                break

        lines = [line for (_, line, _) in current]
        description = "\n".join(lines)
        if len(description) > 3900:
            description = description[:3900] + "\n*(truncated)*"

        ping_user_id = next((ping for (_, _, ping) in current if ping), None)
        if mode == self._WEBHOOK and self.webhook_url:
            self._send_webhook_embed(self.webhook_url, "Log", f"```{description}```", color, ping_user_id=ping_user_id)
        elif mode == self._BOT and self.bot_enabled and self.bot_channel_id:
            self._send_bot_embed("Log", f"```{description}```", color, ping_user_id=ping_user_id)

        if has_more:
            with self._batch_lock:
                timer = threading.Timer(0.5, self._flush_batch, args=(mode,))
                timer.daemon = True
                timer.start()
                self._batch_timers[mode] = timer
        else:
            with self._batch_lock:
                self._batch_timers[mode] = None

    def _send_webhook_embed(self, url: str, title: str, description: str, color: int, fields: list = None, ping_user_id: str = None):
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "footer": {"text": "Roblox Account Manager"},
        }
        if fields:
            embed["fields"] = fields

        payload = {"embeds": [embed], "attachments": []}
        if ping_user_id:
            payload["content"] = f"<@{ping_user_id}>"

        threading.Thread(target=self._post_webhook_payload, args=(url, payload), daemon=True).start()

    def _send_webhook_screenshot(self, url: str, image_bytes: bytes, caption: str):
        def _post():
            try:
                with io.BytesIO(image_bytes) as image_stream:
                    image_stream.seek(0)
                    requests.post(
                        url,
                        data={"content": caption},
                        files={"file": ("screenshot.png", image_stream, "image/png")},
                        timeout=10,
                    )
            except Exception as e:
                print(f"[ERROR] Webhook screenshot send failed: {e}")

        threading.Thread(target=_post, daemon=True).start()

    def _post_webhook_payload(self, url: str, payload: dict):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code not in (200, 204):
                print(f"[Discord] Webhook error {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            print(f"[Discord] Failed to send embed: {e}")

    def _start_bot(self):
        with self._bot_lock:
            token = self.bot_token
            if not self.bot_enabled or not token:
                return
            if self._bot_thread and self._bot_thread.is_alive() and self._bot_token_in_use == token:
                return

        self._stop_bot()

        with self._bot_lock:
            self._bot_token_in_use = token
            self._bot_thread = threading.Thread(target=self._run_bot_thread, daemon=True, name="DiscordBot")
            self._bot_thread.start()

    def _stop_bot(self):
        with self._bot_lock:
            bot = self._bot
            loop = self._bot_loop
            thread = self._bot_thread
            self._bot = None
            self._bot_loop = None
            self._bot_thread = None
            self._bot_token_in_use = None

        if bot and loop and loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._close_bot_resources(bot), loop)
                future.result(timeout=12)
            except Exception:
                pass

        if thread and thread.is_alive():
            thread.join(timeout=12)

    async def _close_bot_resources(self, bot):
        try:
            await bot.close()
        except Exception:
            pass

        try:
            session = getattr(getattr(bot, "http", None), "_HTTPClient__session", None)
            if session and not session.closed:
                await session.close()
        except Exception:
            pass

    def _run_bot_thread(self):
        try:
            asyncio.run(self._bot_main())
        except Exception as e:
            print(f"[ERROR] Discord bot stopped: {e}")
        finally:
            with self._bot_lock:
                self._bot = None
                self._bot_loop = None
                self._bot_thread = None
                self._bot_token_in_use = None

    async def _bot_main(self):
        intents = discord.Intents.default()
        bot = commands.Bot(command_prefix="!", intents=intents)

        with self._bot_lock:
            self._bot = bot
            self._bot_loop = asyncio.get_running_loop()

        self._register_bot_commands(bot)

        @bot.event
        async def on_ready():
            try:
                for guild in bot.guilds:
                    bot.tree.copy_global_to(guild=guild)
                    await bot.tree.sync(guild=guild)
            except Exception as e:
                print(f"[ERROR] Failed to sync Discord slash commands: {e}")

            if self.bot_channel_id:
                await self._bot_send_embed_now(
                    "Connected to Discord!",
                    "Roblox Account Manager started and is now connected.",
                    self.COLOR_SUCCESS,
                )

        await bot.start(self.bot_token)

    def _register_bot_commands(self, bot):
        tree = bot.tree

        @tree.command(name="help", description="Show available bot commands.")
        async def help_command(interaction):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            await self._send_help_embed(interaction)

        @tree.command(name="setlogchannel", description="Use this channel for automatic bot logs.")
        async def setlogchannel_command(interaction):
            self._remember_interaction_channel(interaction, force_save=True)
            await self._defer_interaction(interaction)
            await self._send_interaction_result(
                interaction,
                "Log Channel Updated",
                "This channel is now the default bot log channel.",
                color=self.COLOR_SUCCESS,
            )

        @tree.command(name="accountlist", description="List all accounts, including expired ones.")
        async def accountlist_command(interaction):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            lines = await asyncio.to_thread(self._call_ui_method, "discord_bot_list_accounts")
            await self._send_interaction_result(interaction, "Account List", "\n".join(lines), color=self.COLOR_INFO)

        @tree.command(name="launch", description="Launch an account with optional private server and job ID.")
        @app_commands.describe(
            account_name="Account username",
            place_id="Place ID",
            private_server_id="Optional private server ID or link",
            job_id="Optional job ID",
        )
        async def launch_command(interaction, account_name: str, place_id: str, private_server_id: str = "", job_id: str = ""):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_launch_account",
                account_name,
                place_id,
                private_server_id,
                job_id,
            )
            await self._send_interaction_result(
                interaction,
                "Launch",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="launchuser", description="Launch account to join another user.")
        @app_commands.describe(account_name="Account username", user_to_join="Target username to join")
        async def launchuser_command(interaction, account_name: str, user_to_join: str):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_launch_user",
                account_name,
                user_to_join,
            )
            await self._send_interaction_result(
                interaction,
                "Launch User",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="launchsmall", description="Launch account into the smallest server for a place.")
        @app_commands.describe(account_name="Account username", place_id="Place ID")
        async def launchsmall_command(interaction, account_name: str, place_id: str):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_launch_small",
                account_name,
                place_id,
            )
            await self._send_interaction_result(
                interaction,
                "Launch Small",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="screenshot", description="Send a screenshot from the active machine.")
        async def screenshot_command(interaction):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            image_bytes = await asyncio.to_thread(self._call_ui_method, "discord_bot_capture_screenshot")
            if not image_bytes:
                await interaction.followup.send("Failed to capture a screenshot.")
                return
            file = discord.File(io.BytesIO(image_bytes), filename="screenshot.png")
            await interaction.followup.send(file=file)

        @tree.command(name="autorejoin", description="Start or stop auto-rejoin for an account.")
        @app_commands.describe(action="start or stop", account_name="Account username")
        @app_commands.choices(action=[
            app_commands.Choice(name="start", value="start"),
            app_commands.Choice(name="stop", value="stop"),
        ])
        async def autorejoin_command(interaction, action: str, account_name: str):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_autorejoin_action",
                action,
                account_name,
            )
            await self._send_interaction_result(
                interaction,
                "Auto-Rejoin",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="autorejoinadd", description="Add an account to auto-rejoin config.")
        @app_commands.describe(
            account_name="Account username",
            place_id="Place ID",
            private_server_id="Optional private server ID or link",
            job_id="Optional job ID",
            check_interval="Seconds between checks",
            max_retries="Maximum rejoin attempts",
            check_presence="Verify place before rejoining",
        )
        async def autorejoinadd_command(
            interaction,
            account_name: str,
            place_id: str,
            private_server_id: str = "",
            job_id: str = "",
            check_interval: int = 10,
            max_retries: int = 5,
            check_presence: bool = True,
        ):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_add_autorejoin",
                account_name,
                place_id,
                private_server_id,
                job_id,
                check_interval,
                max_retries,
                check_presence,
            )
            await self._send_interaction_result(
                interaction,
                "Auto-Rejoin Config",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="settings", description="Enable or disable a supported app setting.")
        @app_commands.describe(action="Enable or disable", settings_option="Setting option")
        @app_commands.choices(action=[
            app_commands.Choice(name="enable", value="enable"),
            app_commands.Choice(name="disable", value="disable"),
        ])
        @app_commands.choices(settings_option=[
            app_commands.Choice(name="topmost", value="topmost"),
            app_commands.Choice(name="multi_roblox", value="multi_roblox"),
            app_commands.Choice(name="confirm_before_launch", value="confirm_before_launch"),
            app_commands.Choice(name="multi_select", value="multi_select"),
            app_commands.Choice(name="disable_launch_popup", value="disable_launch_popup"),
            app_commands.Choice(name="auto_tile_windows", value="auto_tile_windows"),
            app_commands.Choice(name="rename_roblox_windows", value="rename_roblox_windows"),
        ])
        async def settings_command(interaction, action: str, settings_option: str):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_settings",
                action,
                settings_option,
            )
            await self._send_interaction_result(
                interaction,
                "Settings",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="robloxlauncher", description="Switch the Roblox launcher used by the app.")
        @app_commands.describe(roblox_launcher="Launcher name")
        @app_commands.choices(roblox_launcher=[
            app_commands.Choice(name="default", value="default"),
            app_commands.Choice(name="bloxstrap", value="bloxstrap"),
            app_commands.Choice(name="fishstrap", value="fishstrap"),
            app_commands.Choice(name="froststrap", value="froststrap"),
            app_commands.Choice(name="voidstrap", value="voidstrap"),
            app_commands.Choice(name="client", value="client"),
        ])
        async def robloxlauncher_command(interaction, roblox_launcher: str):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_set_roblox_launcher",
                roblox_launcher,
            )
            await self._send_interaction_result(
                interaction,
                "Roblox Launcher",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="antiafk", description="Enable or disable Anti-AFK.")
        @app_commands.describe(action="enable or disable")
        @app_commands.choices(action=[
            app_commands.Choice(name="enable", value="enable"),
            app_commands.Choice(name="disable", value="disable"),
        ])
        async def antiafk_command(interaction, action: str):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_set_antiafk",
                action == "enable",
            )
            await self._send_interaction_result(
                interaction,
                "Anti-AFK",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="antiafksettings", description="Update Anti-AFK interval/key/key amount.")
        @app_commands.describe(
            interval_minutes="Interval in minutes (1-19)",
            action_key="Action key or mouse alias",
            key_amount="Press amount (1-10)",
        )
        async def antiafksettings_command(
            interaction,
            interval_minutes: int = None,
            action_key: str = None,
            key_amount: int = None,
        ):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_update_antiafk_settings",
                interval_minutes,
                action_key,
                key_amount,
            )
            await self._send_interaction_result(
                interaction,
                "Anti-AFK Settings",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="closeroblox", description="Force close Roblox by PID or ALL.")
        @app_commands.describe(pid_or_all="Type ALL or a numeric PID")
        async def closeroblox_command(interaction, pid_or_all: str):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_close_roblox",
                pid_or_all,
            )
            await self._send_interaction_result(
                interaction,
                "Close Roblox",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="activelist", description="List active Roblox PID to username mapping.")
        async def activelist_command(interaction):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            lines = await asyncio.to_thread(self._call_ui_method, "discord_bot_active_list")
            await self._send_interaction_result(interaction, "Active Instances", "\n".join(lines), color=self.COLOR_INFO)

        @tree.command(name="setactivewindow", description="Focus a Roblox window by PID.")
        @app_commands.describe(pid="Roblox process PID")
        async def setactivewindow_command(interaction, pid: int):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_set_active_window",
                pid,
            )
            await self._send_interaction_result(
                interaction,
                "Set Active Window",
                result,
                color=self._result_color(result),
            )

        @tree.command(name="addaccount", description="Add account from .ROBLOSECURITY cookie.")
        @app_commands.describe(cookie="Full .ROBLOSECURITY cookie")
        async def addaccount_command(interaction, cookie: str):
            self._remember_interaction_channel(interaction)
            await self._defer_interaction(interaction)
            result = await asyncio.to_thread(
                self._call_ui_method,
                "discord_bot_import_cookie",
                cookie,
            )
            await self._send_interaction_result(
                interaction,
                "Add Account",
                result,
                color=self._result_color(result),
            )

    async def _send_help_embed(self, interaction):
        embed = self._styled_embed(
            "Bot Commands",
            "Use the grouped commands below.",
            self.COLOR_INFO,
        )

        sections = {
            "Launch": [
                "/launch <account_name> <place_id> [private_server_id] [job_id]",
                "/launchuser <account_name> <user_to_join>",
                "/launchsmall <account_name> <place_id>",
            ],
            "Auto-Rejoin": [
                "/autorejoin <start|stop> <account_name>",
                "/autorejoinadd <account_name> <place_id> ...",
            ],
            "Settings": [
                "/settings <enable|disable> <option>",
                "/robloxlauncher <launcher>",
                "/antiafk <enable|disable>",
                "/antiafksettings [interval_minutes] [action_key] [key_amount]",
            ],
            "Accounts": [
                "/accountlist",
                "/addaccount <cookie>",
            ],
            "System": [
                "/activelist",
                "/setactivewindow <PID>",
                "/closeroblox <PID|ALL>",
                "/screenshot",
                "/setlogchannel",
                "/help",
            ],
        }

        for name, commands_list in sections.items():
            embed.add_field(name=name, value="\n".join(commands_list), inline=False)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

    def _result_color(self, text: str) -> int:
        lowered = (text or "").strip().lower()
        if lowered.startswith(("failed", "invalid", "unsupported", "error")):
            return self.COLOR_ERROR
        return self.COLOR_SUCCESS

    async def _defer_interaction(self, interaction):
        """Acknowledge slash command quickly to avoid Discord timeout."""
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True)
        except Exception:
            pass

    def _remember_interaction_channel(self, interaction, force_save: bool = False):
        channel_id = getattr(interaction, "channel_id", None)
        if not channel_id:
            return

        cfg = self.bot_cfg
        if cfg.get("channel_id") == channel_id and not force_save:
            return

        cfg["channel_id"] = channel_id
        self.settings["discord_bot"] = cfg
        self._save_settings()

    def _save_settings(self):
        if not self.app:
            return
        try:
            self.app._run_on_ui_thread(self.app.save_settings, wait=False)
        except Exception:
            pass

    def _call_ui_method(self, method_name: str, *args):
        if not self.app:
            raise RuntimeError("UI bridge is not available.")
        method = getattr(self.app, method_name)
        return self.app._run_on_ui_thread(method, *args)

    def _styled_embed(self, title: str, description: str, color: int):
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Roblox Account Manager")
        return embed

    async def _send_interaction_result(self, interaction, title: str, text: str, color: int = None):
        body = (text or "").strip() or "Done."
        use_color = color if color is not None else self.COLOR_INFO

        if len(body) > 3900:
            file = discord.File(io.BytesIO(body.encode("utf-8")), filename="response.txt")
            if interaction.response.is_done():
                await interaction.followup.send(content=title, file=file)
            else:
                await interaction.response.send_message(content=title, file=file)
            return

        embed = self._styled_embed(title, body, use_color)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

    def _send_bot_embed(self, title: str, description: str, color: int, fields: list = None, ping_user_id: str = None):
        if not self.bot_channel_id:
            return
        self._run_bot_coroutine(self._bot_send_embed_now(title, description, color, fields=fields, ping_user_id=ping_user_id))

    def _send_bot_file(self, file_bytes: bytes, filename: str, caption: str = ""):
        if not self.bot_channel_id:
            return
        self._run_bot_coroutine(self._bot_send_file_now(file_bytes, filename, caption))

    def _run_bot_coroutine(self, coroutine):
        loop = self._bot_loop
        if not loop or not loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(coroutine, loop)
        except Exception:
            pass

    async def _bot_send_embed_now(self, title: str, description: str, color: int, fields: list = None, ping_user_id: str = None):
        bot = self._bot
        channel_id = self.bot_channel_id
        if not bot or not channel_id:
            return

        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception as e:
                print(f"[ERROR] Failed to fetch Discord bot channel: {e}")
                return

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Roblox Account Manager")
        for field in fields or []:
            embed.add_field(
                name=field.get("name", "Field"),
                value=field.get("value", ""),
                inline=field.get("inline", False),
            )

        content = f"<@{ping_user_id}>" if ping_user_id else None
        try:
            await channel.send(content=content, embed=embed)
        except Exception as e:
            print(f"[ERROR] Failed to send Discord bot embed: {e}")

    async def _bot_send_file_now(self, file_bytes: bytes, filename: str, caption: str):
        bot = self._bot
        channel_id = self.bot_channel_id
        if not bot or not channel_id:
            return

        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception as e:
                print(f"[ERROR] Failed to fetch Discord bot channel: {e}")
                return

        try:
            await channel.send(content=caption or None, file=discord.File(io.BytesIO(file_bytes), filename=filename))
        except Exception as e:
            print(f"[ERROR] Failed to send Discord bot file: {e}")
