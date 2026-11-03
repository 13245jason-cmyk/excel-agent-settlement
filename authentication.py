"""Password authentication primitives. No passwords or report data are persisted here."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Mapping

ENVIRONMENTS = {"production": "正式使用", "staging": "內部測試"}
ITERATIONS = 600_000
IDLE_TIMEOUT = 30 * 60
SESSION_LIFETIME = 8 * 60 * 60
USERNAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")


class AuthConfigurationError(ValueError):
    pass


def _parts(encoded: str) -> tuple[int, bytes, bytes]:
    try:
        algorithm, count, salt, digest = encoded.split("$")
        iterations = int(count)
        salt_bytes = base64.b64decode(salt, altchars=b"-_", validate=True)
        digest_bytes = base64.b64decode(digest, altchars=b"-_", validate=True)
        if algorithm != "pbkdf2_sha256" or not ITERATIONS <= iterations <= 2_000_000:
            raise ValueError
        if not 16 <= len(salt_bytes) <= 32 or len(digest_bytes) != 32:
            raise ValueError
        return iterations, salt_bytes, digest_bytes
    except (ValueError, TypeError, AttributeError) as exc:
        raise AuthConfigurationError("password_hash 格式錯誤，請使用 tools/create_user.py 產生。") from exc


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError("密碼長度必須為 12–256 個字元。")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "$".join(("pbkdf2_sha256", str(ITERATIONS), base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode()))


def verify_password(password: str, encoded: str) -> bool:
    count, salt, expected = _parts(encoded)
    if not isinstance(password, str) or len(password) > 256:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, count)
    return hmac.compare_digest(candidate, expected)


@dataclass(frozen=True)
class Account:
    username: str
    display_name: str
    password_hash: str
    environments: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps([self.password_hash, self.environments, self.display_name]).encode()).hexdigest()


def read_accounts(config: Mapping, environment: str) -> dict[str, Account]:
    if environment not in ENVIRONMENTS:
        raise AuthConfigurationError("未知的部署環境。")
    deployment = config.get("deployment", {})
    if not isinstance(deployment, Mapping) or deployment.get("environment") != environment:
        raise AuthConfigurationError(f"此入口必須使用 deployment.environment = \"{environment}\"。")
    users = config.get("users")
    if not isinstance(users, Mapping) or not users:
        raise AuthConfigurationError("尚未設定登入帳號，請在 Streamlit Secrets 設定 users。")
    accounts = {}
    for username, record in users.items():
        if not isinstance(username, str) or not USERNAME.fullmatch(username):
            raise AuthConfigurationError("帳號限 1–64 位小寫英數字、點、底線與連字號。")
        if not isinstance(record, Mapping):
            raise AuthConfigurationError("users 帳號設定格式錯誤。")
        encoded = record.get("password_hash")
        _parts(encoded)
        environments = record.get("environments")
        if not isinstance(environments, list) or not environments or any(not isinstance(e, str) or e not in ENVIRONMENTS for e in environments):
            raise AuthConfigurationError("每個帳號必須設定 environments：production 或 staging。")
        display = record.get("display_name", username)
        if not isinstance(display, str) or not display.strip() or len(display) > 80:
            raise AuthConfigurationError("display_name 必須為 1–80 個字元。")
        accounts[username] = Account(username, display, encoded, tuple(sorted(set(environments))))
    if not any(environment in a.environments for a in accounts.values()):
        raise AuthConfigurationError("此環境沒有可登入的帳號，請檢查 environments。")
    return accounts


class LoginLimiter:
    """Process-wide throttling shared by sessions; reset on application restart."""
    def __init__(self, clock=time.time):
        self.clock = clock
        self._failures: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()
        self._dummy_hash = hash_password(secrets.token_urlsafe(24))

    def authenticate(self, accounts: dict[str, Account], username: str, password: str, environment: str) -> Account | None:
        username = username.strip().lower()
        account = accounts.get(username)
        key = (environment, username if account else "__unknown__")
        # Serialize checks to prevent concurrent requests bypassing the attempt limit.
        with self._lock:
            now = self.clock()
            failures = [t for t in self._failures.get(key, []) if now - t < 120]
            if len(failures) >= 5:
                self._failures[key] = failures
                return None
            valid = verify_password(password, account.password_hash if account else self._dummy_hash)
            if account and valid and environment in account.environments:
                self._failures.pop(key, None)
                return account
            self._failures[key] = failures + [now]
            return None


def start_session(account: Account, environment: str, now: float) -> dict:
    return {"username": account.username, "environment": environment, "fingerprint": account.fingerprint, "issued_at": now, "last_seen": now}


def session_account(session: object, accounts: dict[str, Account], environment: str, now: float) -> Account | None:
    if not isinstance(session, dict):
        return None
    try:
        account = accounts.get(session["username"])
        issued, seen = session["issued_at"], session["last_seen"]
        if not account or environment not in account.environments or session["environment"] != environment:
            return None
        if not hmac.compare_digest(session["fingerprint"], account.fingerprint):
            return None
        if not issued <= seen <= now or now - seen >= IDLE_TIMEOUT or now - issued >= SESSION_LIFETIME:
            return None
        return account
    except (KeyError, TypeError, ValueError):
        return None
