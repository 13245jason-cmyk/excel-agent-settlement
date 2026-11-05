from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

import app_ui
import limited_report
import limited_ui
from limited_report import LimitedReportError, checked_upload, validate_report
from settlement import parse_report

ROOT = Path(__file__).parents[1]


@pytest.fixture
def allowed(monkeypatch):
    from test_sports_settlement import sports_report
    data = sports_report()
    monkeypatch.setattr(limited_report, 'ALLOWED_REPORT_SHA256', sha256(data).hexdigest())
    monkeypatch.setattr(limited_report, 'ALLOWED_REPORT_SIZE', len(data))
    return data


def file(data, name='synthetic.xlsx'):
    uploaded = BytesIO(data)
    uploaded.name = name
    return uploaded


def test_exact_bytes_are_accepted_even_when_renamed(allowed):
    validate_report(allowed)
    snapshot = checked_upload(file(allowed, 'renamed.xlsx'))
    assert snapshot.getvalue() == allowed and snapshot.name == 'renamed.xlsx'


def test_same_filename_or_same_size_cannot_bypass_the_fingerprint(allowed):
    altered = bytes([allowed[0] ^ 1]) + allowed[1:]
    assert len(altered) == len(allowed)
    with pytest.raises(LimitedReportError):
        checked_upload(file(altered))


@pytest.mark.parametrize('data', [b'', b'not an Excel', None, 'text'])
def test_unapproved_content_is_rejected(allowed, data):
    with pytest.raises(LimitedReportError):
        validate_report(data)


def test_resaved_workbook_is_rejected_even_with_identical_financial_cells(allowed):
    wb = load_workbook(BytesIO(allowed))
    wb.properties.description = 'synthetic resaved workbook'
    output = BytesIO()
    wb.save(output)
    wb.close()
    modified = output.getvalue()
    assert parse_report(BytesIO(modified)) == parse_report(BytesIO(allowed))
    with pytest.raises(LimitedReportError):
        validate_report(modified)


def test_downstream_receives_only_the_verified_snapshot(allowed):
    class ChangingUpload:
        name = 'synthetic.xlsx'
        calls = 0
        def getvalue(self):
            self.calls += 1
            return allowed if self.calls == 1 else b'unapproved replacement'
    original = ChangingUpload()
    snapshot = checked_upload(original)
    assert original.calls == 1 and snapshot.getvalue() == allowed


def test_limited_entry_opens_without_secrets_or_login(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Limited entry must not use an authentication gate')
    monkeypatch.setattr(app_ui, 'require_login', forbidden)
    at = AppTest.from_file(ROOT / 'limited_app.py', default_timeout=30).run()
    assert not at.exception
    assert len(at.get('file_uploader')) == 1
    assert not any(t.label in ('帳號', '密碼') for t in at.text_input)
    assert not any('登入' in b.label or '歷史' in b.label for b in at.button)
    assert at.text_input(key='limited_rate_Casino1').label == '真人一館 倍率'
    assert at.text_input(key='limited_rate_Casino2').label == '真人二館 倍率'
    assert at.text_input(key='limited_rate_Sports').label == '體育 倍率'
    assert len(at.metric) == 0 and len(at.get('download_button')) == 0


def test_only_approved_report_calculates_in_all_modes(allowed, monkeypatch, tmp_path):
    monkeypatch.setattr(limited_ui, 'upload_report', lambda: file(allowed))
    monkeypatch.setattr(app_ui, 'BASE_DIR', tmp_path)
    at = AppTest.from_file(ROOT / 'limited_app.py', default_timeout=30).run()
    assert not at.exception
    at.text_input(key='limited_rate_Sports').set_value('0.01')
    at.text_input(key='limited_ratio').set_value('0.5').run()
    for mode, amount in [('整體代理結算', '31.37'), ('單一會員佣金', '-29.92'), ('單一下線代理佣金', '-48.71')]:
        at.radio(key='limited_calculation_mode').set_value(mode).run()
        assert not at.exception
        assert next(m.value for m in at.metric if m.label == '最終結算') == amount
        assert len(at.get('download_button')) == 1
    assert not list(tmp_path.rglob('*.json'))
    assert not any('歷史' in h.value for h in at.subheader)


@pytest.mark.parametrize('mode', ['整體代理結算', '單一會員佣金', '單一下線代理佣金'])
def test_rejected_file_is_never_parsed_or_rendered(allowed, monkeypatch, mode):
    monkeypatch.setattr(limited_ui, 'upload_report', lambda: file(b'not approved'))
    def forbidden(*args, **kwargs):
        raise AssertionError('Unapproved content reached report processing')
    monkeypatch.setattr(limited_ui, 'parse_uploaded_report', forbidden)
    monkeypatch.setattr(limited_ui, 'render_member_commission', forbidden)
    at = AppTest.from_file(ROOT / 'limited_app.py', default_timeout=30).run()
    at.radio(key='limited_calculation_mode').set_value(mode).run()
    assert not at.exception
    assert any('只接受指定的原始報表' in e.value for e in at.error)
    assert len(at.metric) == 0 and len(at.get('download_button')) == 0


def test_invalid_or_removed_file_clears_previous_results(allowed, monkeypatch):
    current = file(allowed)
    monkeypatch.setattr(limited_ui, 'upload_report', lambda: current)
    at = AppTest.from_file(ROOT / 'limited_app.py', default_timeout=30).run()
    assert at.metric and 'parsed_upload' in at.session_state
    current = file(b'changed report', 'synthetic.xlsx')
    at.run()
    assert at.error and len(at.metric) == 0 and len(at.get('download_button')) == 0
    assert 'parsed_upload' not in at.session_state
    current = file(allowed)
    at.run()
    assert at.metric
    current = None
    at.run()
    assert len(at.metric) == 0 and len(at.get('download_button')) == 0
    assert 'parsed_upload' not in at.session_state


def test_anonymous_settings_do_not_leak_between_sessions(allowed, monkeypatch):
    monkeypatch.setattr(limited_ui, 'upload_report', lambda: file(allowed))
    first = AppTest.from_file(ROOT / 'limited_app.py', default_timeout=30).run()
    first.text_input(key='limited_rate_Slots').set_value('0.03').run()
    second = AppTest.from_file(ROOT / 'limited_app.py', default_timeout=30).run()
    assert second.text_input(key='limited_rate_Slots').value == '0.0258'
    assert second.text_input(key='limited_ratio').value == '0.8'


def test_downloads_are_identified_as_limited(allowed, monkeypatch):
    monkeypatch.setattr(limited_ui, 'upload_report', lambda: file(allowed))
    names = []
    monkeypatch.setattr(limited_ui.st, 'download_button', lambda *args, **kwargs: names.append(kwargs['file_name']))
    at = AppTest.from_file(ROOT / 'limited_app.py', default_timeout=30).run()
    for mode in ['整體代理結算', '單一會員佣金', '單一下線代理佣金']:
        at.radio(key='limited_calculation_mode').set_value(mode).run()
        assert not at.exception and names[-1].startswith('限制版_')
