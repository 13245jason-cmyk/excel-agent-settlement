"""Initialize durable approval tables; do not print database credentials."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from approvals import ApprovalStore
from runtime_database import database_url

if __name__ == '__main__':
    try:
        url = database_url(direct=True)
    except ValueError:
        raise SystemExit('請先執行 neon deploy 或設定 DATABASE_URL_UNPOOLED。')
    owner = os.environ.get('APPROVAL_ADMIN_EMAIL')
    if not url or not owner:
        raise SystemExit('請先在安全環境設定資料庫連線與 APPROVAL_ADMIN_EMAIL。')
    try:
        ApprovalStore.connect(url, [owner]).initialize()
    except Exception:
        raise SystemExit('資料庫初始化失敗，請檢查權限、連線與 TLS 設定；未輸出機密資訊。')
    print('授權資料表初始化完成。')
