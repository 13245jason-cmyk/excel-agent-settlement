import io
import time
from pathlib import Path
from dataclasses import replace
from decimal import Decimal

import pytest
from openpyxl import Workbook
from streamlit.testing.v1 import AppTest
from streamlit.proto.TextInput_pb2 import TextInput

import app_ui
from access import account_data_dir, login_limiter
from authentication import Account, hash_password, start_session
from settlement import load_settings

PASSWORD = "synthetic-ui-password-2026"


@pytest.fixture(scope="module")
def account():
    return Account("ui_owner", "內部使用者", hash_password(PASSWORD), ("production", "staging"))


@pytest.fixture(autouse=True)
def clean_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(app_ui, "BASE_DIR", tmp_path)
    login_limiter.clear()


def app(account, environment="production", permissions=None):
    entry = "app.py" if environment == "production" else "staging_app.py"
    at = AppTest.from_file(Path(__file__).parents[1] / entry, default_timeout=15)
    at.secrets["deployment"] = {"environment": environment}
    at.secrets["users"] = {account.username: {
        "display_name": account.display_name, "password_hash": account.password_hash,
        "environments": permissions or list(account.environments),
    }}
    return at


def login(at, password=PASSWORD):
    at.text_input(key="login_username").set_value("ui_owner")
    at.text_input(key="login_password").set_value(password)
    at.button[0].click().run()
    return at


def test_anonymous_has_no_financial_controls(account):
    at = app(account).run()
    assert not at.exception
    assert len(at.get("file_uploader")) == 0
    assert len(at.dataframe) == 0
    assert not any(t.value == "我的歷史報表紀錄" for t in at.subheader)
    assert at.text_input(key="login_password").proto.type == TextInput.PASSWORD


def test_missing_secrets_or_environment_mismatch_stays_locked(account):
    at = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    assert not at.exception
    assert at.error
    assert len(at.get("file_uploader")) == 0
    at = app(account)
    at.secrets["deployment"] = {"environment": "staging"}
    at.run()
    assert not at.exception
    assert at.error
    assert len(at.get("file_uploader")) == 0


def test_wrong_password_and_wrong_environment_never_open_report(account):
    at = login(app(account).run(), "incorrect-password")
    assert at.error
    assert len(at.get("file_uploader")) == 0
    at = app(account, "staging", ["production"]).run()
    assert at.error  # No allowed account in this deployment: fail closed.
    assert len(at.get("file_uploader")) == 0


def test_login_save_logout_and_relogin_isolates_user_data(account, tmp_path):
    at = login(app(account).run())
    assert not at.exception
    assert len(at.get("file_uploader")) == 1
    at.text_input(key="rate_Slots").set_value("0.03")
    next(b for b in at.button if b.label == "儲存設定").click().run()
    path = account_data_dir(tmp_path, "production", account) / "settings.json"
    assert load_settings(path)["rates"]["Slots"] == "0.03"
    assert not account_data_dir(tmp_path, "staging", account).exists()
    # No report bytes, rate widgets, or identity may survive logout.
    at.session_state["parsed_upload"] = {"digest": "test", "report": {"private": "synthetic"}}
    at.button(key="logout").click().run()
    assert len(at.get("file_uploader")) == 0
    assert "parsed_upload" not in at.session_state
    assert "authenticated_session" not in at.session_state
    assert "rate_Slots" not in at.session_state
    login(at)
    assert at.text_input(key="rate_Slots").value == "0.03"


def test_test_environment_banner_and_no_shared_settings(account, tmp_path):
    production = account_data_dir(tmp_path,"production",account)
    production.mkdir(parents=True)
    (production / "settings.json").write_text('{"rates":{"Slots":"0.5","MiniGame":"0.5","Casino1":"0.5","Casino2":"0.5"},"settlement_ratio":"0.5"}')
    at = login(app(account, "staging").run())
    assert not at.exception
    assert any("內部測試環境" in w.value for w in at.warning)
    assert at.text_input(key="rate_Slots").value == "0.0258"


def test_expired_or_revoked_session_clears_report_state(account):
    for expire in (True, False):
        at = app(account)
        at.session_state["authenticated_session"] = start_session(account,"production",time.time()-1900 if expire else time.time())
        at.session_state["parsed_upload"] = {"digest":"private","report":{}}
        if not expire:
            at.secrets["users"]["ui_owner"]["password_hash"] = hash_password("rotated-test-password")
        at.run()
        assert not at.exception
        assert len(at.get("file_uploader")) == 0
        assert "parsed_upload" not in at.session_state


def test_report_computation_still_uses_only_present_games(account, monkeypatch):
    wb = Workbook()
    ws = wb.active
    ws.title = "下線代理"
    ws.append(["遊戲分類", "有效投注", "輸贏金額"])
    ws.append(["Slots",100,-10])
    ws2 = wb.create_sheet("直屬會員")
    ws2.append(["遊戲分類", "有效投注", "輸贏金額"])
    buf=io.BytesIO();wb.save(buf);buf.seek(0);buf.name="synthetic.xlsx"
    monkeypatch.setattr(app_ui.st,"file_uploader",lambda *a,**k:buf)
    at = login(app(account).run())
    assert not at.exception
    assert at.metric[0].value == "-10.00"
    assert at.metric[1].value == "2.58"
    assert at.metric[3].value == "-5.94"
    assert len(at.dataframe[0].value) == 1
    assert at.dataframe[0].value.iloc[0]["遊戲類型"] == "Slots"
