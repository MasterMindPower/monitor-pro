import os
import sys
import json
import time
import subprocess
from script1_fetcher import parse_ist_date_to_epoch

TWO_MINUTES_MS = 2 * 60 * 1000

def log_print(*args, **kwargs):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return
    print(*args, **kwargs)

def check_expiry_and_run():
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cookies_json_path = os.path.join(repo_dir, "cookies.json")
    fetcher_script = os.path.join(repo_dir, "scripts", "script1_fetcher.py")

    needs_refresh = False

    if not os.path.exists(cookies_json_path):
        log_print("[CHECKER] cookies.json does not exist. Initial fetch required.")
        needs_refresh = True
    else:
        try:
            with open(cookies_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list) or len(data) == 0:
                log_print("[CHECKER] cookies.json is empty or invalid. Initial fetch required.")
                needs_refresh = True
            else:
                now_epoch = int(time.time() * 1000)

                for item in data:
                    name = item.get("playlist_name") or f"ID {item.get('playlist_id', 'Unknown')}"
                    epoch = item.get("expires_epoch")

                    if not epoch:
                        epoch = parse_ist_date_to_epoch(item.get("expires"))

                    if not epoch:
                        log_print(f"[CHECKER] Playlist '{name}' has no valid expiry timestamp. Triggering refresh.")
                        needs_refresh = True
                        break

                    # Check if stream expires within 2 minutes or is already expired
                    if (now_epoch + TWO_MINUTES_MS) >= epoch:
                        log_print(f"[CHECKER] Playlist '{name}' is expiring soon/expired (Expiry: {item.get('expires')}). Triggering refresh.")
                        needs_refresh = True
                        break

        except Exception as e:
            log_print(f"[CHECKER] Error reading cookies.json ({e}). Triggering refresh.")
            needs_refresh = True

    if needs_refresh:
        log_print("[CHECKER] Launching script1_fetcher.py...")
        res = subprocess.run([sys.executable, fetcher_script], env=os.environ)
        if res.returncode != 0:
            log_print(f"[CHECKER ERROR] script1_fetcher.py failed with return code {res.returncode}")
            sys.exit(res.returncode)
    else:
        log_print("[CHECKER] All monitored playlists are valid and active. No refresh required at this time.")

if __name__ == "__main__":
    check_expiry_and_run()
