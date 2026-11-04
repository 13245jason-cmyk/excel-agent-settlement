import pytest
from runtime_database import database_url

KEYS=['APPROVAL_DATABASE_URL','DATABASE_URL','APPROVAL_DATABASE_URL_UNPOOLED','DATABASE_URL_UNPOOLED']


@pytest.fixture(autouse=True)
def clean_variables(monkeypatch):
    for key in KEYS:monkeypatch.delenv(key,raising=False)


def test_neon_local_env_and_direct_url(tmp_path):
    (tmp_path/'.env.local').write_text('DATABASE_URL=postgresql://synthetic-pooler/db\nDATABASE_URL_UNPOOLED=postgresql://synthetic-direct/db\n')
    assert database_url(root=tmp_path)=='postgresql://synthetic-pooler/db'
    assert database_url(root=tmp_path,direct=True)=='postgresql://synthetic-direct/db'


def test_process_env_wins_over_files(tmp_path,monkeypatch):
    (tmp_path/'.env.local').write_text('DATABASE_URL=postgresql://file/db\n')
    monkeypatch.setenv('DATABASE_URL','postgresql://process/db')
    assert database_url(root=tmp_path)=='postgresql://process/db'


def test_secrets_win_without_reading_neon_files(tmp_path):
    (tmp_path/'.env.local').write_text('DATABASE_URL=postgresql://neon/db\n')
    assert database_url({'approval_db':{'url':'postgresql://existing/db'}},root=tmp_path)=='postgresql://existing/db'


def test_local_over_default_env(tmp_path):
    (tmp_path/'.env.local').write_text('DATABASE_URL=postgresql://local/db\n')
    (tmp_path/'.env').write_text('DATABASE_URL=postgresql://base/db\n')
    assert database_url(root=tmp_path)=='postgresql://local/db'


def test_missing_database_stays_closed(tmp_path):
    with pytest.raises(ValueError):database_url(root=tmp_path)
