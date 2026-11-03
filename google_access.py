"""Google OIDC gate and approval UI. No client-supplied email can authorize access."""
import hashlib
import time
from urllib.parse import urlparse

import streamlit as st

from authentication import Account, ENVIRONMENTS, IDLE_TIMEOUT, SESSION_LIFETIME
from approvals import ApprovalError, ApprovalStore, GOOGLE_METADATA, verified_identity


def clear(*, preserve_controls=False):
    controls = {'google_login', 'submit_access_request', 'refresh_access'}
    for key in list(st.session_state):
        if not preserve_controls or key not in controls:
            del st.session_state[key]


def validate_config(config, environment):
    if config.get('deployment', {}).get('environment') != environment:
        raise ApprovalError('部署環境與入口不一致')
    auth = config.get('auth', {})
    google = auth.get('google', {})
    redirect = auth.get('redirect_uri', '')
    if urlparse(redirect).scheme != 'https' or urlparse(redirect).path != '/oauth2callback':
        raise ApprovalError('Google callback 必須是該站 HTTPS 網址的 /oauth2callback')
    if len(auth.get('cookie_secret', '')) < 32 or not google.get('client_id') or not google.get('client_secret'):
        raise ApprovalError('Google OAuth 設定不完整')
    if google.get('server_metadata_url') != GOOGLE_METADATA:
        raise ApprovalError('Google discovery URL 不正確')
    admins = config.get('authorization', {}).get('admin_emails')
    if not isinstance(admins, list) or not admins or any(not isinstance(e,str) or '@' not in e for e in admins):
        raise ApprovalError('請設定授權管理者 Google 電子郵件')
    if not config.get('approval_db', {}).get('url'):
        raise ApprovalError('尚未設定持久授權資料庫')
    return tuple(sorted(e.strip().lower() for e in admins))


@st.cache_resource
def get_store(url, admins):
    store = ApprovalStore.connect(url, admins)
    store.initialize()
    return store


def setup(environment):
    try:
        config = st.secrets.to_dict()
        admins = validate_config(config, environment)
        return config, get_store(config['approval_db']['url'], admins)
    except Exception:
        clear()
        st.error('Google 登入／授權資料庫尚未設定完成或暫時無法連線，報表功能已鎖定。請聯絡管理者。')
        st.stop()


def google_identity():
    if not st.user.is_logged_in:
        clear(preserve_controls=True)
        st.subheader('使用 Google 帳號登入')
        st.caption('登入後仍需提出申請，經管理者核准才可使用報表。')
        if st.button('使用 Google 登入', key='google_login'):
            st.login('google')
        st.stop()
    try:
        identity = verified_identity(st.user.to_dict())
    except ApprovalError as exc:
        clear()
        st.error(str(exc))
        if st.button('重新登入 Google'):
            st.logout()
        st.stop()
    # Account changes cannot retain another identity's uploaded report/widgets.
    if st.session_state.get('google_subject') != identity.subject:
        clear()
        st.session_state.google_subject = identity.subject
        st.session_state.google_issued_at = time.time()
    with st.sidebar:
        st.write(f'Google：{identity.email}')
        if st.button('登出 Google', key='google_logout'):
            clear()
            st.logout()
    return identity


@st.fragment(run_every=30)
def approval_watchdog(environment):
    try:
        config = st.secrets.to_dict()
        admins = validate_config(config, environment)
        store = get_store(config['approval_db']['url'], admins)
        identity = verified_identity(st.user.to_dict())
        authorized = store.status(identity, environment) == 'approved'
        now = time.time()
        active = now-st.session_state.get('google_last_seen',0) < IDLE_TIMEOUT
        active = active and now-st.session_state.get('google_issued_at',0) < SESSION_LIFETIME
        if authorized and active:
            return  # Watchdog never extends idle time.
    except Exception:
        pass
    clear()
    st.session_state.google_reauthenticate = True
    st.rerun(scope='app')


def require_google_access(environment):
    _, store = setup(environment)
    if st.session_state.get('google_reauthenticate'):
        st.warning('登入已逾時、授權已變更或資料庫暫時無法連線，請重新登入。')
        if st.button('重新登入 Google'):
            clear()
            st.logout()
        st.stop()
    identity = google_identity()
    try:
        status = store.status(identity, environment)
    except Exception:
        clear()
        st.error('無法驗證授權，報表功能已鎖定。請稍後再試。')
        st.stop()
    if status != 'approved':
        # Remove financial state on revocation even while Google login remains valid.
        for key in list(st.session_state):
            if not key.startswith('google_') and key not in {'submit_access_request', 'refresh_access'}:
                del st.session_state[key]
        st.subheader(f'{ENVIRONMENTS[environment]}使用申請')
        messages = {'unrequested':'你尚未取得此環境的使用權限。', 'pending':'申請已送出，等待管理者核准。',
                    'rejected':'申請未核准，請聯絡管理者。', 'revoked':'使用權限已停用，請聯絡管理者。'}
        st.info(messages.get(status, '尚未取得授權'))
        if status == 'unrequested' and st.button('提出使用申請', key='submit_access_request'):
            try:
                store.request(identity, environment)
                st.rerun()
            except Exception:
                st.error('申請送出失敗，請稍後再試。')
        if st.button('重新檢查授權', key='refresh_access'):
            st.rerun()
        st.stop()
    now = time.time()
    if now-st.session_state.get('google_last_seen',now) >= IDLE_TIMEOUT or now-st.session_state['google_issued_at'] >= SESSION_LIFETIME:
        clear()
        st.session_state.google_reauthenticate = True
        st.rerun()
    st.session_state.google_last_seen = now
    approval_watchdog(environment)
    # Stable Google subject, never user-entered email, owns the local account directory.
    return Account('google:'+identity.subject, identity.name, hashlib.sha256(identity.subject.encode()).hexdigest(), (environment,))
