"""Session-local upload via a self-contained Streamlit component."""
from __future__ import annotations

import base64
import binascii
import io
from pathlib import Path
import secrets

import streamlit as st
import streamlit.components.v1 as components

MAX_MOBILE_UPLOAD_BYTES = 10 * 1024 * 1024
_upload_component = components.declare_component(
    "compatible_report_upload", path=str(Path(__file__).parent / "components" / "mobile_upload")
)


class UploadError(ValueError):
    pass


def decode_upload(payload: object) -> io.BytesIO | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise UploadError("上傳資料格式錯誤，請重新選擇檔案。")
    name, size, encoded = (payload.get(key) for key in ("name", "size", "data"))
    if not isinstance(name, str) or not name.lower().endswith(".xlsx") or len(name) > 255:
        raise UploadError("請選擇檔名以 .xlsx 結尾的 Excel 報表。")
    if type(size) is not int or size <= 0 or size > MAX_MOBILE_UPLOAD_BYTES:
        raise UploadError("手機相容上傳僅接受非空白且不超過 10 MB 的報表。")
    max_encoded = 4 * ((MAX_MOBILE_UPLOAD_BYTES + 2) // 3)
    if not isinstance(encoded, str) or len(encoded) > max_encoded:
        raise UploadError("上傳內容超過上限或格式錯誤，請重新選擇檔案。")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UploadError("上傳內容不完整，請重新選擇檔案。") from exc
    if len(data) != size:
        raise UploadError("上傳檔案大小不符，請重新選擇檔案。")
    uploaded = io.BytesIO(data)
    uploaded.name = name.replace("\\", "/").rsplit("/", 1)[-1]
    return uploaded


def compatible_file_uploader() -> io.BytesIO | None:
    # A new login gets a new component instance; another user's file cannot recur.
    if "compatible_upload_nonce" not in st.session_state:
        st.session_state.compatible_upload_nonce = secrets.token_hex(16)
    payload = _upload_component(
        max_bytes=MAX_MOBILE_UPLOAD_BYTES,
        key=f"compatible_report_{st.session_state.compatible_upload_nonce}",
        default=None,
    )
    try:
        return decode_upload(payload)
    except UploadError as exc:
        st.error(str(exc))
        return None
