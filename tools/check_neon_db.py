"""Verify actual service lifecycle using unique synthetic rows, then clean them up."""
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import delete, text
from approvals import ApprovalStore, GoogleIdentity, audit, grants
from runtime_database import database_url


def main():
    owner = os.environ.get('APPROVAL_ADMIN_EMAIL')
    if not owner:
        raise ValueError('請設定 APPROVAL_ADMIN_EMAIL')
    store = ApprovalStore.connect(database_url(), [owner])
    subject = 'neon-setup-check-' + uuid.uuid4().hex
    admin = GoogleIdentity('setup-operator', owner.lower(), 'Setup operator')
    user = GoogleIdentity(subject, 'synthetic-neon-check@example.invalid', 'Synthetic service check')
    try:
        with store.engine.connect() as conn:
            assert conn.execute(text('SELECT 1')).scalar_one() == 1
        assert store.status(user, 'staging') == 'unrequested'
        assert store.request(user, 'staging') == 'pending'
        row = next(r for r in store.list_requests(admin, 'staging') if r['subject'] == subject)
        store.review(admin, subject, 'staging', 'approved', row['revision'])
        assert store.status(user, 'staging') == 'approved'
        assert store.status(user, 'production') == 'unrequested'
        store.review(admin, subject, 'staging', 'revoked', row['revision']+1)
        assert store.status(user, 'staging') == 'revoked'
        print('NEON SERVICE CHECK PASSED: TLS connection, request, approve, environment isolation, revoke.')
    finally:
        # Only delete the synthetic subject created by THIS invocation.
        with store.engine.begin() as conn:
            conn.execute(delete(audit).where(audit.c.subject == subject))
            conn.execute(delete(grants).where(grants.c.subject == subject))
        store.engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('NEON SERVICE CHECK FAILED: check credentials, network, TLS and schema; no secrets printed.')
