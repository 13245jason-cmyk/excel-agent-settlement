"""Resolve private Neon connection variables without exposing their values."""
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


def database_url(config=None, *, direct=False, root=None):
    # Existing Streamlit Secrets remain authoritative over local development files.
    explicit = (config or {}).get('approval_db', {}).get('url')
    if explicit:
        return explicit
    root = ROOT if root is None else Path(root)
    load_dotenv(root / '.env.local', override=False)
    load_dotenv(root / '.env', override=False)
    keys = ['APPROVAL_DATABASE_URL', 'DATABASE_URL']
    if direct:
        keys = ['APPROVAL_DATABASE_URL_UNPOOLED', 'DATABASE_URL_UNPOOLED'] + keys
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    raise ValueError('尚未設定 approval_db.url、APPROVAL_DATABASE_URL 或 Neon DATABASE_URL')
