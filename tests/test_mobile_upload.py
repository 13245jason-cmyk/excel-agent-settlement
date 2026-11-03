import base64

import pytest

from mobile_upload import MAX_MOBILE_UPLOAD_BYTES, UploadError, decode_upload


def payload(data=b"synthetic bytes", name="report.xlsx"):
    return {"name": name, "size": len(data), "data": base64.b64encode(data).decode()}


def test_decoded_report_preserves_exact_bytes_and_filename():
    data = b"PK\x03\x04\x00\xff\xfe\x01"
    uploaded = decode_upload(payload(data, "測試.xlsx"))
    assert uploaded.name == "測試.xlsx"
    assert uploaded.getvalue() == data
    assert uploaded.tell() == 0
    assert decode_upload(None) is None


@pytest.mark.parametrize("value", [
    [], {}, payload(name="report.xls"), payload(name="report.xlsx.exe"),
    payload(b""), {**payload(), "size": True}, {**payload(), "size": MAX_MOBILE_UPLOAD_BYTES + 1},
    {**payload(), "data": "!!!!"}, {**payload(), "data": "非合法編碼"},
    {**payload(), "size": 1}, {**payload(), "data": 123},
])
def test_invalid_upload_is_explicitly_rejected(value):
    with pytest.raises(UploadError):
        decode_upload(value)


def test_client_size_and_paths_are_not_trusted():
    assert decode_upload(payload(name="C:\\fakepath\\report.xlsx")).name == "report.xlsx"
    assert decode_upload(payload(name="/untrusted/report.xlsx")).name == "report.xlsx"
    with pytest.raises(UploadError):
        decode_upload({**payload(), "size": -1})


def test_encoded_limit_is_checked_before_decoding():
    with pytest.raises(UploadError):
        decode_upload({**payload(), "data": "A" * (4 * ((MAX_MOBILE_UPLOAD_BYTES + 2) // 3) + 1)})
