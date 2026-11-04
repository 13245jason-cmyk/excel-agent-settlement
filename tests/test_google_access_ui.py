import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from sqlalchemy import create_engine

import app_ui
import google_access
from approvals import ApprovalStore, GoogleIdentity, GOOGLE_METADATA

ROOT=Path(__file__).parents[1]
ADMIN=GoogleIdentity('root-sub','owner@example.com','Owner')
USER=GoogleIdentity('user-sub','applicant@example.com','Applicant')


class FakeGoogleUser:
    is_logged_in=True
    identity=USER
    verified=True
    def to_dict(self):
        return dict(iss='https://accounts.google.com',sub=self.identity.subject,email=self.identity.email,
                    email_verified=self.verified,exp=time.time()+3600,name=self.identity.name)


@pytest.fixture
def runtime(monkeypatch,tmp_path):
    store=ApprovalStore(create_engine('sqlite:///'+str(tmp_path/'access.db'),connect_args={'check_same_thread':False}),[ADMIN.email]);store.initialize()
    user=FakeGoogleUser()
    monkeypatch.setattr(google_access.st,'user',user)
    monkeypatch.setattr(google_access,'get_store',lambda *a:store)
    monkeypatch.setattr(app_ui,'BASE_DIR',tmp_path)
    return store,user


def app(environment='production',entry='app.py'):
    at=AppTest.from_file(ROOT/entry,default_timeout=30)
    at.secrets['deployment']={'environment':environment}
    at.secrets['access']={'login_method':'google'}
    at.secrets['auth']={'redirect_uri':'https://synthetic.example/oauth2callback','cookie_secret':'x'*40,'google':{'client_id':'synthetic','client_secret':'synthetic','server_metadata_url':GOOGLE_METADATA}}
    at.secrets['authorization']={'admin_emails':[ADMIN.email]}
    at.secrets['approval_db']={'url':'synthetic-test-database'}
    return at


def test_anonymous_login_and_unverified_have_no_financial_ui(runtime,monkeypatch):
    _,user=runtime;user.is_logged_in=False
    providers=[];monkeypatch.setattr(google_access.st,'login',lambda provider:providers.append(provider))
    at=app().run();assert not at.exception;assert len(at.get('file_uploader'))==0
    at.button(key='google_login').click().run();assert providers==['google']
    user.is_logged_in=True;user.verified=False
    at.run();assert at.error;assert len(at.get('file_uploader'))==0


def test_google_login_requires_approval_and_cannot_use_legacy_session(runtime):
    store,_=runtime
    at=app();at.session_state['authenticated_session']={'username':'owner'};at.run()
    assert not at.exception and len(at.get('file_uploader'))==0
    assert len(at.text_input)==0  # Applicant cannot submit someone else's email.
    at.button(key='submit_access_request').click().run()
    assert store.status(USER,'production')=='pending'
    assert len(at.get('file_uploader'))==0
    store.review(ADMIN,USER.subject,'production','approved',1)
    at.button(key='refresh_access').click().run()
    assert not at.exception and len(at.get('file_uploader'))==1
    assert at.text_input(key='rate_Sports').value=='0'
    at.session_state['parsed_upload']={'digest':'private','report':{}}
    store.review(ADMIN,USER.subject,'production','revoked',2)
    at.run();assert not at.exception;assert len(at.get('file_uploader'))==0
    assert 'parsed_upload' not in at.session_state


def test_production_approval_does_not_open_staging(runtime):
    store,_=runtime;store.request(USER,'production');store.review(ADMIN,USER.subject,'production','approved',1)
    at=app('staging','staging_app.py').run()
    assert not at.exception and len(at.get('file_uploader'))==0
    assert at.button(key='submit_access_request')


def test_admin_portal_denies_users_and_owner_can_approve(runtime):
    store,user=runtime;store.request(USER,'production')
    at=app('admin','approval_app.py').run()
    assert at.error and len(at.dataframe)==0
    user.identity=ADMIN
    at.run();assert not at.exception;assert any('| Google 帳號 |' in m.value for m in at.markdown)
    at.checkbox[0].check().run()
    next(b for b in at.button if b.label=='套用審核決定').click().run()
    assert not at.exception and store.status(USER,'production')=='approved'


def test_db_failure_and_bad_config_never_fall_back_to_password(runtime,monkeypatch):
    store,_=runtime
    at=app();at.secrets['auth']['google']['server_metadata_url']='https://untrusted.example'
    at.run();assert at.error and len(at.get('file_uploader'))==0 and len(at.text_input)==0
    def fail(*a):raise OSError('synthetic unavailable db')
    monkeypatch.setattr(store,'status',fail)
    at=app().run();assert not at.exception and at.error and len(at.get('file_uploader'))==0


def test_google_account_switch_clears_other_users_report(runtime):
    store,user=runtime
    store.request(USER,'production');store.review(ADMIN,USER.subject,'production','approved',1)
    at=app().run();assert len(at.get('file_uploader'))==1
    at.session_state['parsed_upload']={'digest':'synthetic-private-data','report':{}}
    user.identity=GoogleIdentity('second-sub','second@example.com','Second user')
    at.run()
    assert not at.exception and len(at.get('file_uploader'))==0
    assert 'parsed_upload' not in at.session_state
    assert at.session_state['google_subject']=='second-sub'


def test_staging_embedded_management_cannot_change_production(runtime):
    store, user = runtime
    store.request(USER, 'staging')
    store.request(USER, 'production')
    user.identity = ADMIN
    at = app('staging', 'staging_app.py').run()
    at.session_state['approval_environment'] = 'production'
    at.radio(key='google_staging_page').set_value('授權管理').run()
    assert not at.exception
    assert len(at.get('file_uploader')) == 0
    assert len(at.selectbox) == 0 and len(at.dataframe) == 0
    assert not any(r.label == '管理環境' for r in at.radio)
    assert any('此頁只管理「內部測試」' in message.value for message in at.info)
    at.checkbox[0].check().run()
    next(b for b in at.button if b.label == '套用審核決定').click().run()
    assert not at.exception and at.success
    assert store.status(USER, 'staging') == 'approved'
    assert store.status(USER, 'production') == 'pending'
    assert len(store.audit_log(ADMIN, environment='staging')) == 2


def test_member_cannot_forge_staging_management_navigation(runtime, monkeypatch):
    store, _ = runtime
    store.request(USER, 'staging')
    store.review(ADMIN, USER.subject, 'staging', 'approved', 1)
    def forbidden(*args, **kwargs):
        raise AssertionError('An ordinary user must not read applicant records')
    monkeypatch.setattr(store, 'list_requests', forbidden)
    at = app('staging', 'staging_app.py').run()
    at.session_state['google_staging_page'] = '授權管理'
    at.run()
    assert not at.exception and len(at.get('file_uploader')) == 1
    assert not any(r.label == '功能頁面' for r in at.radio)
    assert not any('| Google 帳號 |' in m.value for m in at.markdown)


def test_review_confirmation_binds_to_the_current_decision(runtime, monkeypatch):
    store, user = runtime
    store.request(USER, 'staging')
    user.identity = ADMIN
    at = app('staging', 'staging_app.py').run()
    at.radio(key='google_staging_page').set_value('授權管理').run()
    at.checkbox[0].check().run()
    next(r for r in at.radio if r.label == '審核決定').set_value('rejected').run()
    assert not at.checkbox[0].value
    assert next(b for b in at.button if b.label == '套用審核決定').disabled
    # Simulate a stale event; AppTest correctly forbids clicking disabled widgets.
    real_button = google_access.st.button
    def stale_event(label, *args, **kwargs):
        return True if label == '套用審核決定' else real_button(label, *args, **kwargs)
    monkeypatch.setattr(google_access.st, 'button', stale_event)
    at.run()
    assert store.status(USER, 'staging') == 'pending'


def test_staging_request_approve_and_revoke_through_embedded_ui(runtime):
    store, user = runtime
    applicant = app('staging', 'staging_app.py').run()
    applicant.button(key='submit_access_request').click().run()
    assert store.status(USER, 'staging') == 'pending'
    assert len(applicant.get('file_uploader')) == 0
    user.identity = ADMIN
    manager = app('staging', 'staging_app.py').run()
    manager.radio(key='google_staging_page').set_value('授權管理').run()
    manager.checkbox[0].check().run()
    next(b for b in manager.button if b.label == '套用審核決定').click().run()
    user.identity = USER
    applicant.button(key='refresh_access').click().run()
    assert len(applicant.get('file_uploader')) == 1
    applicant.session_state['member_upload'] = {'private': 'synthetic-report'}
    applicant.session_state['compatible_upload_nonce'] = 'synthetic-instance'
    user.identity = ADMIN
    manager.run()
    manager.radio(key='approval_status_staging').set_value('approved').run()
    next(r for r in manager.radio if r.label == '審核決定').set_value('revoked').run()
    manager.checkbox[0].check().run()
    next(b for b in manager.button if b.label == '套用審核決定').click().run()
    user.identity = USER
    applicant.run()
    assert not applicant.exception and len(applicant.get('file_uploader')) == 0
    assert 'member_upload' not in applicant.session_state
    assert 'compatible_upload_nonce' not in applicant.session_state
    assert store.status(USER, 'staging') == 'revoked'


def test_failed_review_never_reports_success(runtime, monkeypatch):
    store, user = runtime
    store.request(USER, 'staging')
    user.identity = ADMIN
    at = app('staging', 'staging_app.py').run()
    at.radio(key='google_staging_page').set_value('授權管理').run()
    at.checkbox[0].check().run()
    def fail(*args, **kwargs):
        raise OSError('synthetic-private-connection-details')
    monkeypatch.setattr(store, 'review', fail)
    next(b for b in at.button if b.label == '套用審核決定').click().run()
    assert at.error and not at.success
    assert store.status(USER, 'staging') == 'pending'
    assert all('synthetic-private-connection-details' not in e.value for e in at.error)
