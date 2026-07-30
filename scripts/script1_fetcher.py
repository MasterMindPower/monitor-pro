import os
import sys
import json
import re
import time
from datetime import datetime, timezone, timedelta
import requests
from encrypt_helper import decrypt_text, load_dotenv

load_dotenv()

def parse_ist_date_to_epoch(ist_str):
    """
    Parses IST/UTC date strings or exp= tokens into Epoch milliseconds.
    """
    if not ist_str:
        return None
    if isinstance(ist_str, (int, float)):
        return int(ist_str * 1000) if ist_str < 10000000000 else int(ist_str)
    
    str_val = str(ist_str).strip()
    if not str_val:
        return None

    # Check exp=1785196800 or raw numeric string
    exp_match = re.search(r'exp=(\d+)', str_val, re.IGNORECASE)
    if exp_match:
        sec = int(exp_match.group(1))
        return sec * 1000 if sec < 10000000000 else sec

    if re.match(r'^\d{9,13}$', str_val):
        num = int(str_val)
        return num * 1000 if num < 10000000000 else num

    # Pattern: DD-MM-YY - HH:MM AM/PM
    match = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\s*-\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)$', str_val, re.IGNORECASE)
    if match:
        day, month, year, hours, minutes, seconds, ampm = match.groups()
        day, month = day.zfill(2), month.zfill(2)
        if len(year) == 2:
            year = '20' + year
        h = int(hours)
        if ampm.upper() == 'PM' and h < 12:
            h += 12
        if ampm.upper() == 'AM' and h == 12:
            h = 0
        s = seconds.zfill(2) if seconds else '00'
        iso_str = f"{year}-{month}-{day}T{str(h).zfill(2)}:{minutes.zfill(2)}:{s}+05:30"
        try:
            dt = datetime.fromisoformat(iso_str)
            return int(dt.timestamp() * 1000)
        except Exception:
            pass

    return None

def format_epoch_to_ist(epoch_ms):
    """
    Formats Epoch milliseconds to IST date string: DD-MM-YY - HH:MM AM/PM
    """
    if not epoch_ms:
        return "No Expiry Found"
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    dt = datetime.fromtimestamp(epoch_ms / 1000.0, tz=ist_tz)
    return dt.strftime("%d-%m-%y - %I:%M %p")

def fetch_and_update():
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cookies_json_path = os.path.join(repo_dir, "cookies.json")

    url_entries = []
    decrypted_raw = ""

    # Priority 1: Check local plaintext url.json
    local_url_json = os.path.join(repo_dir, "url.json")
    if os.path.exists(local_url_json):
        try:
            with open(local_url_json, "r", encoding="utf-8") as f:
                content = f.read().strip()
            parsed = json.loads(content)
            if isinstance(parsed, list):
                url_entries = parsed
            elif isinstance(parsed, dict):
                url_entries = [parsed]
            if url_entries:
                pass
        except Exception:
            # Fall back to decryption if url.json is not plaintext JSON
            pass

    # Priority 2: Decrypt url-enc.json (or encrypted url.json / url.txt)
    if not url_entries:
        passphrase = os.environ.get("ENCRYPTION_KEY", "").strip() or os.environ.get("PW", "").strip()
        if not passphrase:
            print("[ERROR] ENCRYPTION_KEY environment variable is missing.")
            sys.exit(1)

        enc_file_path = os.path.join(repo_dir, "url-enc.json")
        if not os.path.exists(enc_file_path):
            enc_file_path = os.path.join(repo_dir, "url.json")
        if not os.path.exists(enc_file_path):
            enc_file_path = os.path.join(repo_dir, "url.txt")

        if not os.path.exists(enc_file_path):
            print(f"[ERROR] No valid source file (url.json or url-enc.json) found in {repo_dir}")
            sys.exit(1)

        with open(enc_file_path, "r", encoding="utf-8") as f:
            encrypted_content = f.read().strip()

        try:
            decrypted_raw = decrypt_text(encrypted_content, passphrase)
        except Exception as e:
            print(f"[ERROR] Failed to decrypt {os.path.basename(enc_file_path)}: {e}")
            sys.exit(1)

        try:
            parsed_json = json.loads(decrypted_raw)
            if isinstance(parsed_json, list):
                url_entries = parsed_json
            elif isinstance(parsed_json, dict):
                url_entries = [parsed_json]
        except Exception:
            lines = decrypted_raw.splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "|" in line:
                    parts = line.split("|", 1)
                    url_entries.append({"name": parts[0].strip(), "url": parts[1].strip()})
                else:
                    url_entries.append({"name": f"Playlist_{len(url_entries)+1}", "url": line})

    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    url_log_json_path = os.path.join(repo_dir, "url-log.json")

    results = []
    log_entries = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache"
    }

    ist_tz = timezone(timedelta(hours=5, minutes=30))

    for idx, item in enumerate(url_entries, start=1):
        playlist_id = item.get("id", idx)
        playlist_code = item.get("playlist_code")
        
        refresh_url = item.get("url_refresh_link") or item.get("url") or item.get("playlist_link") or ""
        export_url = item.get("url_export_link") or refresh_url

        type_data = item.get("type_data")
        if not type_data:
            target_url_check = (export_url or refresh_url).lower()
            if "m3u8" in target_url_check:
                type_data = "m3u8"
            elif "json" in target_url_check:
                type_data = "json"
            elif "m3u" in target_url_check:
                type_data = "m3u"
            else:
                type_data = "m3u"

        if not playlist_code:
            match = re.search(r'/(?:export|refresh)/([a-zA-Z0-9]+)', export_url or refresh_url)
            if match:
                playlist_code = match.group(1)
            else:
                playlist_code = str(playlist_id)

        if not refresh_url and not export_url:
            continue

        cookie_val = ""
        expires_str = "No Expiry Found"
        expires_epoch = None
        
        now_ist_str = datetime.now(ist_tz).strftime("%d-%m-%Y %I:%M:%S %p IST")

        # Step 1: Call refresh_url to trigger live refresh on server
        if refresh_url:
            cache_buster_refresh = refresh_url + ("&" if "?" in refresh_url else "?") + f"_t={int(time.time())}"
            try:
                requests.get(cache_buster_refresh, headers=headers, timeout=20)
            except Exception:
                pass

        # Step 2: Fetch export_url to retrieve playlist data & extract cookie / exp
        target_url = export_url if export_url else refresh_url
        cache_buster_export = target_url + ("&" if "?" in target_url else "?") + f"_t={int(time.time())}"
        try:
            res = requests.get(cache_buster_export, headers=headers, timeout=20)
            
            if res.status_code != 200:
                log_msg = f"Fail to get latest at {now_ist_str}"
                log_status = "FAILED"
                cookies_get_val = "no"
                print(f"playlist_{playlist_id} failed")
            else:
                text = res.text
                cookie_match = re.search(r'(?:__hdnea__|hdnea|http-cookie|Cookie|token|auth|wmsAuthSign)=[^\s"\n#]+', text, re.IGNORECASE)
                exp_match = re.search(r'exp=(\d+)', text, re.IGNORECASE)

                if cookie_match:
                    cookie_val = cookie_match.group(0)

                if exp_match:
                    exp_val = int(exp_match.group(1))
                    expires_epoch = exp_val * 1000 if exp_val < 10000000000 else exp_val
                    expires_str = format_epoch_to_ist(expires_epoch)
                else:
                    extracted_epoch = parse_ist_date_to_epoch(text)
                    if extracted_epoch:
                        expires_epoch = extracted_epoch
                        expires_str = format_epoch_to_ist(extracted_epoch)

                log_msg = f"Get latest data at {now_ist_str}"
                log_status = "SUCCESS"
                cookies_get_val = "yes" if (cookie_match or exp_match or expires_epoch or res.status_code == 200) else "no"
                print(f"playlist_{playlist_id} success")

            result_entry = {
                "playlist_id": str(playlist_id),
                "playlist_code": str(playlist_code),
                "type_data": str(type_data),
                "expires": expires_str,
                "expires_epoch": expires_epoch,
                "cookies_get": cookies_get_val,
                "cookies_expires": expires_str,
                "now_active": "inactive",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            results.append(result_entry)

        except Exception:
            log_msg = f"Fail to get latest at {now_ist_str}"
            log_status = "FAILED"
            print(f"playlist_{playlist_id} failed")
            result_entry = {
                "playlist_id": str(playlist_id),
                "playlist_code": str(playlist_code),
                "type_data": str(type_data),
                "expires": expires_str,
                "expires_epoch": expires_epoch,
                "cookies_get": "no",
                "cookies_expires": expires_str,
                "now_active": "inactive",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            results.append(result_entry)

        log_entries.append({
            "playlist_id": str(playlist_id),
            "playlist_code": str(playlist_code),
            "status": log_status,
            "message": log_msg,
            "now_active": "inactive",
            "timestamp": now_ist_str
        })

    # Calculate now_active ranking based on remaining expiration epoch
    valid_items = [r for r in results if r.get("expires_epoch")]
    valid_items.sort(key=lambda x: x["expires_epoch"], reverse=True)

    current_rank = 0
    prev_epoch = None
    rank_counts = {}

    for item in valid_items:
        epoch = item["expires_epoch"]
        if prev_epoch is not None and abs(epoch - prev_epoch) < 10000:
            rank_counts[current_rank] = rank_counts.get(current_rank, 0) + 1
            suffix = "-extra" if rank_counts[current_rank] > 1 else ""
            item["now_active"] = f"active-{current_rank}{suffix}"
        else:
            current_rank += 1
            prev_epoch = epoch
            rank_counts[current_rank] = 1
            item["now_active"] = f"active-{current_rank}"

    # Sync now_active to log_entries
    now_active_map = {r["playlist_id"]: r["now_active"] for r in results}
    for log_item in log_entries:
        log_item["now_active"] = now_active_map.get(log_item["playlist_id"], "inactive")

    # Write output to cookies.json
    with open(cookies_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Write output to url-log.json
    with open(url_log_json_path, "w", encoding="utf-8") as f:
        json.dump(log_entries, f, indent=2)

if __name__ == "__main__":
    fetch_and_update()
