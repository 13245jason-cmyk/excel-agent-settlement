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
    at.run();assert not at.exception;assert len(at.dataframe)>0
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
