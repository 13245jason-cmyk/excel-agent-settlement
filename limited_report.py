"""Exact-file allowlist for the deliberately public limited app."""
from hashlib import sha256
from hmac import compare_digest
from io import BytesIO

ALLOWED_REPORT_SHA256 = "8433f95c88e468e1e14a0096bc28d256d0fbaabf37ee5708105102b95d14ce7e"
ALLOWED_REPORT_SIZE = 15661


class LimitedReportError(ValueError):
    pass


def validate_report(data: bytes) -> None:
    if (not isinstance(data, bytes) or len(data) != ALLOWED_REPORT_SIZE
            or not compare_digest(sha256(data).hexdigest(), ALLOWED_REPORT_SHA256)):
        raise LimitedReportError("限制版只接受指定的原始報表。修改或重新儲存的檔案無法使用，請選擇原始檔。")


def checked_upload(uploaded) -> BytesIO:
    # Read exactly once. All downstream calculations receive this checked snapshot.
    data = uploaded.getvalue()
    validate_report(data)
    snapshot = BytesIO(data)
    snapshot.name = str(uploaded.name).replace("\\", "/").rsplit("/", 1)[-1]
    return snapshot
