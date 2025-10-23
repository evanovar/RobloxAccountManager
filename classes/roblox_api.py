import os
import time
import random
import requests
from utils.ui_helpers import Colors, colored_text

class RobloxAPI:
        try:
            headers = {
                'Cookie': f'.ROBLOSECURITY={roblosecurity_cookie}'
            }

            response = requests.get(
                'https://users.roblox.com/v1/users/authenticated',
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                user_data = response.json()
                return user_data.get('name', 'Unknown')

        except Exception as e:
            print(colored_text(f"Error getting username from API: {e}", Colors.RED))

        return "Unknown"

    @staticmethod
    def get_auth_ticket(roblosecurity_cookie):
        print(f"🎮 Getting authentication ticket for {username}...")
        auth_ticket = RobloxAPI.get_auth_ticket(cookie)

        if not auth_ticket:
            print(colored_text("[ERROR] Failed to get authentication ticket", Colors.RED))
            return False

        print(colored_text("[SUCCESS] Got authentication ticket!", Colors.GREEN))

        if not game_id or game_id == "":
            url = f"roblox://authentication?ticket={auth_ticket}"
            print(f"🚀 Launching Roblox Home...")
            print(f"   Account: {username}")
            try:
                os.system(f'start "" "{url}"')
                print(colored_text("[SUCCESS] Roblox home launched successfully!", Colors.GREEN))
                return True
            except Exception as e:
                print(colored_text(f"[ERROR] Failed to launch Roblox: {e}", Colors.RED))
                return False

        browser_tracker_id = random.randint(55393295400, 55393295500)
        launch_time = int(time.time() * 1000)

        url = (
            "roblox-player:1+launchmode:play+gameinfo:" + auth_ticket +
            "+launchtime:" + str(launch_time) +
            "+placelauncherurl:https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGame" +
            "&browserTrackerId=" + str(browser_tracker_id) +
            "&placeId=" + str(game_id) +
            "&isPlayTogetherGame=false"
        )

        if private_server_id:
            url += "&linkCode=" + private_server_id

        url += (
            "+browsertrackerid:" + str(browser_tracker_id) +
            "+robloxLocale:en_us+gameLocale:en_us"
        )

        print(f"🚀 Launching Roblox...")
        print(f"   Account: {username}")
        print(f"   Game ID: {game_id}")
        if private_server_id:
            print(f"   Private Server: {private_server_id}")

        try:
            os.system(f'start "" "{url}"')
            print(colored_text("[SUCCESS] Roblox launched successfully!", Colors.GREEN))
            return True
        except Exception as e:
            print(colored_text(f"[ERROR] Failed to launch Roblox: {e}", Colors.RED))
            return False

    @staticmethod
    def validate_account(username, cookie):
