import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from approvals import ApprovalError, ApprovalStore, GoogleIdentity, metadata, verified_identity

ADMIN = GoogleIdentity('admin-sub', 'owner@example.com', 'Owner')
USER = GoogleIdentity('user-sub', 'applicant@example.com', 'Applicant')


@pytest.fixture
def store(tmp_path):
    url = os.environ.get('APPROVAL_TEST_DATABASE_URL')
    if url:
        parsed=make_url(url)
        assert parsed.host in ('127.0.0.1','localhost') and parsed.database=='approval_test', 'Only isolated local approval_test DB is allowed'
        engine=create_engine(url, pool_pre_ping=True)
    else:
        engine=create_engine('sqlite:///'+str(tmp_path/'approvals.db'),connect_args={'check_same_thread':False})
    metadata.drop_all(engine)
    service=ApprovalStore(engine,[ADMIN.email]);service.initialize()
    yield service
    metadata.drop_all(engine);engine.dispose()


def claims(**changes):
    return dict(iss='https://accounts.google.com',sub=USER.subject,email=USER.email,email_verified=True,exp=time.time()+3600,name=USER.name)|changes


def test_verified_google_identity():
    assert verified_identity(claims())==USER


@pytest.mark.parametrize('changes',[{'email_verified':False},{'email_verified':'true'},{'iss':'https://untrusted.example'},{'sub':''},{'exp':0},{'exp':float('nan')},{'exp':float('inf')},{'email':'invalid'}])
def test_invalid_identity_denied(changes):
    with pytest.raises(ApprovalError):verified_identity(claims(**changes))


def test_request_approve_environment_and_revoke(store):
    assert store.status(USER,'production')=='unrequested'
    assert store.request(USER,'production')=='pending'
    assert store.request(USER,'production')=='pending'
    rows=store.list_requests(ADMIN,'production','pending');assert len(rows)==1
    store.review(ADMIN,USER.subject,'production','approved',rows[0]['revision'])
    assert store.status(USER,'production')=='approved'
    assert store.status(USER,'staging')=='unrequested'
    assert store.request(USER,'production')=='approved'
    revision=store.list_requests(ADMIN,'production')[0]['revision']
    store.review(ADMIN,USER.subject,'production','revoked',revision)
    assert store.request(USER,'production')=='revoked'
    assert len(store.audit_log(ADMIN))==3


def test_nonadmin_cannot_manage_even_after_approval(store):
    store.request(USER,'production')
    with pytest.raises(ApprovalError):store.list_requests(USER,'production')
    with pytest.raises(ApprovalError):store.audit_log(USER)
    with pytest.raises(ApprovalError):store.review(USER,USER.subject,'production','approved',1)
    assert store.status(USER,'production')=='pending'


def test_conflicting_admin_decision_not_overwritten(store):
    store.request(USER,'staging')
    store.review(ADMIN,USER.subject,'staging','approved',1)
    with pytest.raises(ApprovalError):store.review(ADMIN,USER.subject,'staging','rejected',1)
    assert store.status(USER,'staging')=='approved'
    assert len(store.audit_log(ADMIN))==2


def test_rejected_user_cannot_resubmit_to_reset_status(store):
    store.request(USER,'production');store.review(ADMIN,USER.subject,'production','rejected',1)
    assert store.request(USER,'production')=='rejected'
    assert store.status(USER,'production')=='rejected'


def test_same_subject_changed_email_requires_review_again(store):
    store.request(USER,'production');store.review(ADMIN,USER.subject,'production','approved',1)
    changed=replace(USER,email='changed@example.com')
    assert store.status(changed,'production')=='unrequested'
    assert store.request(changed,'production')=='pending'
    assert store.status(USER,'production')=='unrequested'
    assert store.list_requests(ADMIN,'production')[0]['revision']==3


def test_same_email_different_subject_gets_no_access(store):
    store.request(USER,'production');store.review(ADMIN,USER.subject,'production','approved',1)
    assert store.status(replace(USER,subject='different-subject'),'production')=='unrequested'


def test_approval_survives_new_store_instance(store):
    store.request(USER,'production');store.review(ADMIN,USER.subject,'production','approved',1)
    other=ApprovalStore(store.engine,[ADMIN.email])
    assert other.status(USER,'production')=='approved'


def test_concurrent_requests_create_only_one_pending_grant(store):
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert set(pool.map(lambda _:store.request(USER,'production'),range(3)))=={'pending'}
    assert len(store.list_requests(ADMIN,'production'))==1
    assert len(store.audit_log(ADMIN))==1


def test_online_store_refuses_local_sqlite():
    with pytest.raises(ApprovalError):ApprovalStore.connect('sqlite:///insecure.db',[ADMIN.email])


def test_postgres_transport_always_verifies_tls(monkeypatch):
    captured={}
    def fake_engine(url,**kwargs):
        captured.update(kwargs)
        return object()
    monkeypatch.setattr('approvals.create_engine',fake_engine)
    ApprovalStore.connect('postgresql://test:test@db.example/approvals?sslmode=disable',[ADMIN.email])
    assert captured['connect_args']['sslmode']=='verify-full'
    assert captured['connect_args']['sslrootcert']


def test_audit_environment_filter_happens_before_returning_records(store):
    store.request(USER, 'production')
    store.request(USER, 'staging')
    store.review(ADMIN, USER.subject, 'staging', 'approved', 1)
    records = store.audit_log(ADMIN, environment='staging')
    assert len(records) == 2
    assert {row['environment'] for row in records} == {'staging'}
    assert len(store.audit_log(ADMIN, environment='production')) == 1
    with pytest.raises(ApprovalError):
        store.audit_log(USER, environment='staging')
    with pytest.raises(ApprovalError):
        store.audit_log(ADMIN, environment='untrusted')
