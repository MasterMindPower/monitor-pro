import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from encrypt_helper import load_dotenv, encrypt_text

load_dotenv()

def push_updates():
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    url_json_path = os.path.join(repo_dir, "url.json")
    url_enc_path = os.path.join(repo_dir, "url-enc.json")
    checker_path = os.path.join(repo_dir, "scripts", "script2_checker.py")

    passphrase = os.environ.get("ENCRYPTION_KEY", "").strip() or os.environ.get("PW", "").strip()
    if not passphrase:
        print("[PUSH ERROR] ENCRYPTION_KEY environment variable is missing in .env")
        sys.exit(1)

    if not os.path.exists(url_json_path):
        print(f"[PUSH ERROR] Local url.json file not found at: {url_json_path}")
        sys.exit(1)

    # 0. Sync remote changes first to prevent rebase conflicts
    subprocess.run(["git", "pull", "origin", "main", "--rebase", "-X", "ours"], cwd=repo_dir)

    # 1. Encrypt url.json -> url-enc.json
    print("[PUSH 1/4] Encrypting local url.json into url-enc.json...")
    try:
        with open(url_json_path, "r", encoding="utf-8") as f:
            content = f.read()
        encrypted_cipher = encrypt_text(content, passphrase)
        with open(url_enc_path, "w", encoding="utf-8") as f:
            f.write(encrypted_cipher)
        print("[SUCCESS] url-enc.json updated successfully.")
    except Exception as e:
        print(f"[PUSH ERROR] Failed to encrypt url.json: {e}")
        sys.exit(1)

    # 2. Run script2_checker.py to update cookies.json and url-log.json locally
    print("[PUSH 2/4] Refreshing stream cookies and updating url-log.json...")
    res = subprocess.run([sys.executable, checker_path], cwd=repo_dir)
    if res.returncode != 0:
        print(f"[WARNING] script2_checker.py exited with code {res.returncode}")

    # 3. Commit changes to Git with Date and Time timestamp
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_str = datetime.now(ist_tz).strftime("%d-%m-%Y %I:%M:%S %p IST")
    raw_msg = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    commit_msg = raw_msg if raw_msg else f"Update playlists, cookies.json & url-enc.json - {now_str}"
    print(f"[PUSH 3/4] Staging and committing files to Git with message: '{commit_msg}'...")

    # Stage files (url.json and .env remain ignored by .gitignore)
    subprocess.run(["git", "add", "."], cwd=repo_dir)

    commit_res = subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_dir)

    # 4. Push to GitHub
    print("[PUSH 4/4] Pushing changes to GitHub repository...")
    push_res = subprocess.run(["git", "push"], cwd=repo_dir)
    if push_res.returncode != 0:
        print("[NOTICE] Retrying push with remote sync...")
        subprocess.run(["git", "pull", "origin", "main", "--rebase", "-X", "theirs"], cwd=repo_dir)
        push_res = subprocess.run(["git", "push"], cwd=repo_dir)

    if push_res.returncode == 0:
        print("\n=======================================================")
        print("[SUCCESS] All latest data pushed to GitHub successfully!")
        print("  - url.json: Saved locally (git-ignored)")
        print("  - url-enc.json: Encrypted and pushed to GitHub")
        print("  - cookies.json & url-log.json: Updated & pushed")
        print("=======================================================\n")
    else:
        print(f"\n[NOTICE] Git push finished with return code {push_res.returncode}.")
        print("If remote is not set yet, initialize git remote: git remote add origin <URL> and run 'git push -u origin main'.\n")

if __name__ == "__main__":
    push_updates()
