from dataclasses import replace
from pathlib import Path

import pytest

from access import account_data_dir
from authentication import (
    Account, AuthConfigurationError, IDLE_TIMEOUT, SESSION_LIFETIME,
    LoginLimiter, hash_password, read_accounts, session_account, start_session,
    verify_password,
)

PASSWORD = "synthetic-test-password-2026"


@pytest.fixture(scope="module")
def account():
    return Account("alice", "測試使用者", hash_password(PASSWORD), ("production", "staging"))


def config(account, environment="production"):
    return {"deployment": {"environment": environment}, "users": {account.username: {
        "display_name": account.display_name, "password_hash": account.password_hash,
        "environments": list(account.environments),
    }}}


def test_hash_password_salt_and_verification(account):
    assert verify_password(PASSWORD, account.password_hash)
    assert not verify_password("incorrect-password", account.password_hash)
    assert hash_password(PASSWORD) != account.password_hash
    assert not verify_password("x" * 257, account.password_hash)
    with pytest.raises(ValueError):
        hash_password("short")


@pytest.mark.parametrize("bad", ["password123456", "pbkdf2_sha256$1$invalid$invalid", "pbkdf2_sha256$999999999$invalid$invalid", None])
def test_plaintext_or_invalid_hash_rejected(account, bad):
    c = config(account)
    c["users"]["alice"]["password_hash"] = bad
    with pytest.raises(AuthConfigurationError):
        read_accounts(c, "production")


def test_missing_or_wrong_deployment_is_closed(account):
    for c in [{}, {"users": {}}, config(account, "staging")]:
        with pytest.raises(AuthConfigurationError):
            read_accounts(c, "production")


def test_account_permissions_and_removed_users(account):
    restricted = replace(account, environments=("staging",))
    limiter = LoginLimiter()
    assert limiter.authenticate({"alice": restricted}, "alice", PASSWORD, "production") is None
    assert limiter.authenticate({"alice": restricted}, "alice", PASSWORD, "staging") == restricted
    with pytest.raises(AuthConfigurationError):
        read_accounts(config(restricted), "production")
    session = start_session(account, "production", 1000)
    assert session_account(session, {}, "production", 1001) is None


def test_failed_attempts_block_all_sessions_then_expire(account):
    now = [1000.0]
    limiter = LoginLimiter(clock=lambda: now[0])
    for _ in range(5):
        assert limiter.authenticate({"alice": account}, "alice", "incorrect", "production") is None
    assert limiter.authenticate({"alice": account}, "alice", PASSWORD, "production") is None
    now[0] += 121
    assert limiter.authenticate({"alice": account}, " ALICE ", PASSWORD, "production") == account


def test_session_expiry_and_permission_changes(account):
    session = start_session(account, "production", 1000)
    accounts = {"alice": account}
    assert session_account(session, accounts, "production", 1001) == account
    assert session_account(session, accounts, "staging", 1001) is None
    assert session_account(session, accounts, "production", 1000 + IDLE_TIMEOUT) is None
    fresh = session | {"last_seen": 1000 + SESSION_LIFETIME - 1}
    assert session_account(fresh, accounts, "production", 1000 + SESSION_LIFETIME) is None
    assert session_account(session, {"alice": replace(account, password_hash=hash_password("changed-test-password"))}, "production", 1001) is None
    assert session_account({"username": "alice"}, accounts, "production", 1001) is None


def test_data_separated_by_account_and_environment(account, tmp_path):
    a = account_data_dir(tmp_path, "production", account)
    b = account_data_dir(tmp_path, "staging", account)
    c = account_data_dir(tmp_path, "production", replace(account, username="bob"))
    assert len({a,b,c}) == 3
    assert a.is_relative_to(tmp_path / "data" / "production")
    assert account.username not in str(a.relative_to(tmp_path))
