"""Google identities and durable, environment-scoped approval decisions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import math
import ssl
import time

from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table,
                        create_engine, insert, select, update)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url

ENVIRONMENTS = ('production', 'staging')
STATUSES = ('pending', 'approved', 'rejected', 'revoked')
GOOGLE_METADATA = 'https://accounts.google.com/.well-known/openid-configuration'


class ApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    name: str


def verified_identity(claims, now=None):
    """Only call with claims verified by Streamlit/Authlib, never browser inputs."""
    now = time.time() if now is None else now
    if claims.get('iss') not in ('https://accounts.google.com', 'accounts.google.com'):
        raise ApprovalError('登入身分不是 Google')
    if claims.get('email_verified') is not True:
        raise ApprovalError('Google 電子郵件尚未驗證')
    subject, email = claims.get('sub'), claims.get('email')
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
        raise ApprovalError('缺少 Google 身分識別')
    if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ApprovalError('Google 電子郵件格式錯誤')
    expiry = claims.get('exp')
    if isinstance(expiry, bool) or not isinstance(expiry, (int,float)) or not math.isfinite(expiry) or not expiry > now:
        raise ApprovalError('Google 登入已逾時，請登出後重新登入')
    name = claims.get('name', email)
    return GoogleIdentity(subject, email.lower(), str(name)[:200])


metadata = MetaData()
grants = Table('settlement_access_grants', metadata,
    Column('subject', String(255), primary_key=True),
    Column('environment', String(20), primary_key=True),
    Column('email', String(254), nullable=False),
    Column('name', String(200), nullable=False),
    Column('status', String(20), nullable=False),
    Column('revision', Integer, nullable=False),
    Column('requested_at', DateTime(timezone=True), nullable=False),
    Column('updated_at', DateTime(timezone=True), nullable=False))
audit = Table('settlement_access_audit', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('subject', String(255), nullable=False),
    Column('environment', String(20), nullable=False),
    Column('actor', String(254), nullable=False),
    Column('action', String(40), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False))


class ApprovalStore:
    def __init__(self, engine, admin_emails):
        self.engine = engine
        self.admin_emails = frozenset(e.strip().lower() for e in admin_emails)
        if not self.admin_emails:
            raise ApprovalError('尚未設定授權管理者')

    @classmethod
    def connect(cls, url, admin_emails):
        parsed = make_url(url)
        if parsed.get_backend_name() != 'postgresql':
            raise ApprovalError('線上授權資料庫必須使用 PostgreSQL，不可使用本機暫存檔')
        parsed = parsed.set(drivername='postgresql+psycopg')
        ca = ssl.get_default_verify_paths().cafile or '/etc/ssl/certs/ca-certificates.crt'
        engine = create_engine(parsed, pool_pre_ping=True, pool_size=2, max_overflow=1,
                               connect_args={'sslmode':'verify-full', 'sslrootcert':ca, 'connect_timeout':10})
        return cls(engine, admin_emails)

    def initialize(self):
        metadata.create_all(self.engine)

    def is_admin(self, identity):
        return identity.email in self.admin_emails

    @staticmethod
    def _environment(environment):
        if environment not in ENVIRONMENTS:
            raise ApprovalError('未知的授權環境')

    def status(self, identity, environment):
        self._environment(environment)
        if self.is_admin(identity):
            return 'approved'
        with self.engine.connect() as conn:
            row = conn.execute(select(grants).where(grants.c.subject==identity.subject,
                               grants.c.environment==environment)).mappings().first()
        if row is None or row['email'] != identity.email:
            return 'unrequested'
        return row['status']

    def request(self, identity, environment):
        self._environment(environment)
        now = datetime.now(timezone.utc)
        try:
            with self.engine.begin() as conn:
                existing = conn.execute(select(grants).where(grants.c.subject==identity.subject,
                         grants.c.environment==environment).with_for_update()).mappings().first()
                if existing and existing['email'] == identity.email:
                    return existing['status']  # A rejected/revoked user cannot self-approve or reset it.
                if existing:
                    conn.execute(update(grants).where(grants.c.subject==identity.subject,
                        grants.c.environment==environment).values(email=identity.email, name=identity.name,
                        status='pending', revision=existing['revision']+1, requested_at=now, updated_at=now))
                else:
                    conn.execute(insert(grants).values(subject=identity.subject, environment=environment,
                        email=identity.email, name=identity.name, status='pending', revision=1,
                        requested_at=now, updated_at=now))
                conn.execute(insert(audit).values(subject=identity.subject, environment=environment,
                             actor=identity.email, action='request', created_at=now))
            return 'pending'
        except IntegrityError:
            # Concurrent first submissions have one unique grant, never overwrite a decision.
            return self.status(identity, environment)

    def _require_admin(self, actor):
        if not self.is_admin(actor):
            raise ApprovalError('僅管理者可以查看或修改授權')

    def list_requests(self, actor, environment, status=None):
        self._require_admin(actor)
        self._environment(environment)
        query = select(grants).where(grants.c.environment==environment)
        if status is not None:
            if status not in STATUSES:
                raise ApprovalError('未知的申請狀態')
            query = query.where(grants.c.status==status)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query.order_by(grants.c.requested_at.desc())).mappings()]

    def review(self, actor, subject, environment, decision, expected_revision):
        self._require_admin(actor)
        self._environment(environment)
        if decision not in ('approved', 'rejected', 'revoked'):
            raise ApprovalError('不合法的審核決定')
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            result = conn.execute(update(grants).where(grants.c.subject==subject,
                grants.c.environment==environment, grants.c.revision==expected_revision).values(
                status=decision, revision=expected_revision+1, updated_at=now))
            if result.rowcount != 1:
                raise ApprovalError('這筆申請已被更新，請重新整理後再操作')
            conn.execute(insert(audit).values(subject=subject, environment=environment,
                         actor=actor.email, action=decision, created_at=now))

    def audit_log(self, actor, environment=None):
        self._require_admin(actor)
        query = select(audit)
        if environment is not None:
            self._environment(environment)
            query = query.where(audit.c.environment == environment)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query.order_by(audit.c.id.desc()).limit(200)).mappings()]
