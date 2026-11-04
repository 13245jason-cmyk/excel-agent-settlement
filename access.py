"""Streamlit access gate, called before any financial data or controls are loaded."""
from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

from authentication import (
    Account, AuthConfigurationError, ENVIRONMENTS, LoginLimiter,
    read_accounts, session_account, start_session,
)


@st.cache_resource
def login_limiter() -> LoginLimiter:
    return LoginLimiter()


def clear_session() -> None:
    for key in list(st.session_state):
        del st.session_state[key]


@st.fragment(run_every=30)
def session_watchdog(environment: str) -> None:
    """Timer checks never renew inactivity; expire already-rendered financial UI."""
    try:
        accounts = read_accounts(st.secrets.to_dict(), environment)
        account = session_account(st.session_state.get("authenticated_session"), accounts, environment, time.time())
    except (AuthConfigurationError, FileNotFoundError):
        account = None
    if account is None:
        clear_session()
        st.rerun(scope="app")


def require_login(environment: str) -> Account:
    try:
        method = st.secrets.get("access", {}).get("login_method", "password")
    except FileNotFoundError:
        method = "password"
    if method == "google":
        from google_access import require_google_access
        return require_google_access(environment)
    if method != "password":
        clear_session()
        st.error("登入方式設定錯誤，報表功能已鎖定。")
        st.stop()
    try:
        config = st.secrets.to_dict()
        accounts = read_accounts(config, environment)
    except (AuthConfigurationError, FileNotFoundError) as exc:
        clear_session()
        st.error("登入服務尚未設定完成，報表功能已鎖定。請聯絡管理者設定 Streamlit Secrets。")
        if isinstance(exc, AuthConfigurationError):
            st.caption(str(exc))
        st.stop()

    now = time.time()
    session = st.session_state.get("authenticated_session")
    account = session_account(session, accounts, environment, now)
    if account:
        st.session_state.authenticated_session["last_seen"] = now
        with st.sidebar:
            st.write(f"已登入：{account.display_name}")
            st.caption(f"{ENVIRONMENTS[environment]} · 閒置 30 分鐘需重新登入")
            if st.button("登出", key="logout", use_container_width=True):
                clear_session()
                st.rerun()
        session_watchdog(environment)
        return account

    if session is not None:
        clear_session()
        st.info("登入已逾時、權限已變更或帳號已停用，請重新登入。")
    st.subheader(f"{ENVIRONMENTS[environment]}登入")
    st.caption("僅限管理者預先建立的帳號，不開放自行註冊。")
    with st.form("login_form", clear_on_submit=True):
        username = st.text_input("帳號", max_chars=64, key="login_username")
        password = st.text_input("密碼", type="password", max_chars=256, key="login_password")
        submitted = st.form_submit_button("登入", use_container_width=True)
    if submitted:
        account = login_limiter().authenticate(accounts, username, password, environment)
        if account:
            clear_session()
            st.session_state.authenticated_session = start_session(account, environment, time.time())
            st.rerun()
        st.error("登入失敗：帳號、密碼或環境權限不正確。連續失敗請稍候 2 分鐘再試。")
    st.stop()


def account_data_dir(base: Path, environment: str, account: Account) -> Path:
    import hashlib
    if environment not in ENVIRONMENTS:
        raise ValueError("未知的部署環境")
    account_key = hashlib.sha256(account.username.encode()).hexdigest()
    return base / "data" / environment / account_key
