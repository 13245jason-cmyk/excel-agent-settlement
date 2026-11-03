"""Generate an account TOML block without putting plaintext passwords in arguments."""
import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from authentication import ENVIRONMENTS, USERNAME, hash_password


def main():
    parser = argparse.ArgumentParser(description="產生 Streamlit Secrets 帳號設定（不寫入任何檔案）")
    parser.add_argument("--username", required=True)
    parser.add_argument("--environment", choices=ENVIRONMENTS, required=True)
    args = parser.parse_args()
    if not USERNAME.fullmatch(args.username):
        parser.error("帳號限小寫英數字、點、底線、連字號，最多64位")
    password = getpass.getpass("密碼（12–256字元，不顯示）: ")
    if password != getpass.getpass("再次輸入密碼: "):
        parser.error("兩次密碼不相同")
    try:
        encoded = hash_password(password)
    except ValueError as exc:
        parser.error(str(exc))
    print(f'\n[deployment]\nenvironment = "{args.environment}"\n')
    print(f'[users.{json.dumps(args.username)}]')
    print(f'display_name = {json.dumps(args.username)}')
    print(f'password_hash = "{encoded}"')
    print(f'environments = ["{args.environment}"]')


if __name__ == "__main__":
    main()
