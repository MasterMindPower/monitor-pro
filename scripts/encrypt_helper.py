import sys
import os
import secrets
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

def load_dotenv():
    """
    Automatically loads key-value pairs from .env if present in root directory.
    """
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(repo_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and not os.environ.get(k):
                        os.environ[k] = v

load_dotenv()

def derive_fernet_key(passphrase: str) -> bytes:
    """
    Derives a valid 32-byte urlsafe base64 Fernet key from any string passphrase.
    """
    salt = b'monitor_pro_salt_2026'
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode('utf-8')))

def encrypt_text(plain_text: str, passphrase: str) -> str:
    key = derive_fernet_key(passphrase)
    f = Fernet(key)
    return f.encrypt(plain_text.encode('utf-8')).decode('utf-8')

def decrypt_text(cipher_text: str, passphrase: str) -> str:
    key = derive_fernet_key(passphrase)
    f = Fernet(key)
    return f.decrypt(cipher_text.strip().encode('utf-8')).decode('utf-8')

def update_env_file(new_passphrase: str):
    """
    Updates or creates .env with the new ENCRYPTION_KEY and PW.
    """
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(repo_dir, ".env")
    
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    found_key = False
    found_pw = False

    for line in lines:
        if line.strip().startswith("ENCRYPTION_KEY="):
            new_lines.append(f"ENCRYPTION_KEY={new_passphrase}\n")
            found_key = True
        elif line.strip().startswith("PW="):
            new_lines.append(f"PW={new_passphrase}\n")
            found_pw = True
        else:
            new_lines.append(line)

    if not found_key:
        new_lines.append(f"ENCRYPTION_KEY={new_passphrase}\n")
    if not found_pw:
        new_lines.append(f"PW={new_passphrase}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ["ENCRYPTION_KEY"] = new_passphrase
    os.environ["PW"] = new_passphrase
    print(f"[ENV UPDATED] Set ENCRYPTION_KEY and PW to: '{new_passphrase}' in .env")

def change_passphrase(old_pw: str, new_pw: str):
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    url_path = os.path.join(repo_dir, "url-enc.json")
    if not os.path.exists(url_path):
        url_path = os.path.join(repo_dir, "url.json")

    if not os.path.exists(url_path):
        print(f"[ERROR] Neither url-enc.json nor url.json exists in {repo_dir}.")
        return

    with open(url_path, "r", encoding="utf-8") as f:
        cipher = f.read().strip()

    try:
        plain = decrypt_text(cipher, old_pw)
    except Exception as e:
        print(f"[ERROR] Could not decrypt {os.path.basename(url_path)} using old password '{old_pw}': {e}")
        return

    new_cipher = encrypt_text(plain, new_pw)
    with open(url_path, "w", encoding="utf-8") as f:
        f.write(new_cipher)

    update_env_file(new_pw)

    print("\n=======================================================")
    print("[SUCCESS] Password changed successfully!")
    print(f"  Old Password: {old_pw}")
    print(f"  New Password: {new_pw}")
    print(f"  Updated files: {os.path.basename(url_path)} (re-encrypted) & .env (local)")
    print("=======================================================")
    print("IMPORTANT: Remember to update your GitHub Repository Secret!")
    print("  Go to GitHub Repo -> Settings -> Secrets and variables -> Actions")
    print(f"  Update secret 'ENCRYPTION_KEY' value to: {new_pw}")
    print("=======================================================\n")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Encrypt:        python scripts/encrypt_helper.py encrypt <passphrase> [url_or_json_file]")
        print("  Decrypt:        python scripts/encrypt_helper.py decrypt <passphrase> [file_or_text]")
        print("  Change Password: python scripts/encrypt_helper.py change-pw <old_pw> <new_pw>")
        print("  Generate Key:   python scripts/encrypt_helper.py generate-key")
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "change-pw":
        if len(sys.argv) < 4:
            env_key = os.environ.get("ENCRYPTION_KEY", "")
            if len(sys.argv) == 3 and env_key:
                old_pw = env_key
                new_pw = sys.argv[2]
            else:
                print("Usage: python scripts/encrypt_helper.py change-pw <old_pw> <new_pw>")
                sys.exit(1)
        else:
            old_pw = sys.argv[2]
            new_pw = sys.argv[3]

        change_passphrase(old_pw, new_pw)

    elif action == "generate-key":
        new_key = secrets.token_hex(16)
        old_pw = os.environ.get("ENCRYPTION_KEY", "admin123")
        print(f"[GENERATED NEW KEY]: {new_key}")
        
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        url_path = os.path.join(repo_dir, "url-enc.json")
        if not os.path.exists(url_path):
            url_path = os.path.join(repo_dir, "url.json")

        if os.path.exists(url_path):
            change_passphrase(old_pw, new_key)
        else:
            update_env_file(new_key)

    elif action == "encrypt":
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        passphrase = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("ENCRYPTION_KEY", "admin123")
        
        # Default target is local url.json if present
        default_target = os.path.join(repo_dir, "url.json")
        target = sys.argv[3] if len(sys.argv) > 3 else (sys.argv[2] if len(sys.argv) > 2 and os.path.exists(sys.argv[2]) else default_target)

        if os.path.exists(target):
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()
            encrypted = encrypt_text(content, passphrase)
            out_file = os.path.join(repo_dir, "url-enc.json")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(encrypted)
            print(f"[SUCCESS] Encrypted content from {os.path.basename(target)} written to: {out_file}")
        else:
            encrypted = encrypt_text(target, passphrase)
            out_file = os.path.join(repo_dir, "url-enc.json")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(encrypted)
            print(f"[SUCCESS] Encrypted string written to: {out_file}")

    elif action == "decrypt":
        passphrase = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("ENCRYPTION_KEY", "admin123")
        target = sys.argv[3] if len(sys.argv) > 3 else "url-enc.json"

        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_target = os.path.join(repo_dir, target) if not os.path.exists(target) else target
        if not os.path.exists(file_target) and target == "url-enc.json":
            file_target = os.path.join(repo_dir, "url.json")

        if os.path.exists(file_target):
            with open(file_target, "r", encoding="utf-8") as f:
                content = f.read()
            decrypted = decrypt_text(content, passphrase)
            print(f"[DECRYPTED CONTENT ({os.path.basename(file_target)})]:\n{decrypted}")
            with open(file_target, "r", encoding="utf-8") as f:
                content = f.read()
            decrypted = decrypt_text(content, passphrase)
            print(f"[DECRYPTED CONTENT ({os.path.basename(file_target)})]:\n{decrypted}")
        else:
            decrypted = decrypt_text(target, passphrase)
            print(f"[DECRYPTED TEXT]:\n{decrypted}")
    else:
        print("Invalid action. Use 'encrypt', 'decrypt', 'change-pw', or 'generate-key'.")
