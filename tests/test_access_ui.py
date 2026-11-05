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
    at = AppTest.from_file(Path(__file__).parents[1] / entry, default_timeout=30)
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
    at.text_input(key="rate_電子類型").set_value("0.03")
    next(b for b in at.button if b.label == "儲存設定").click().run()
    path = account_data_dir(tmp_path, "production", account) / "settings.json"
    assert load_settings(path)["rates"]["電子類型"] == "0.03"
    assert not account_data_dir(tmp_path, "staging", account).exists()
    # No report bytes, rate widgets, or identity may survive logout.
    at.session_state["parsed_upload"] = {"digest": "test", "report": {"private": "synthetic"}}
    at.button(key="logout").click().run()
    assert len(at.get("file_uploader")) == 0
    assert "parsed_upload" not in at.session_state
    assert "authenticated_session" not in at.session_state
    assert "rate_電子類型" not in at.session_state
    login(at)
    assert at.text_input(key="rate_電子類型").value == "0.03"


def test_test_environment_banner_and_no_shared_settings(account, tmp_path):
    production = account_data_dir(tmp_path,"production",account)
    production.mkdir(parents=True)
    (production / "settings.json").write_text('{"rates":{"Slots":"0.5","MiniGame":"0.5","Casino1":"0.5","Casino2":"0.5"},"settlement_ratio":"0.5"}')
    at = login(app(account, "staging").run())
    assert not at.exception
    assert any("內部測試環境" in w.value for w in at.warning)
    assert at.text_input(key="rate_電子類型").value == "0.0258"


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
    assert len(at.dataframe) == 0
    table = next(m for m in at.markdown if m.value.startswith('| 遊戲類型 |'))
    assert not table.proto.allow_html
    assert len(table.value.splitlines()) == 3
    assert "| 電子類型 | 100.00 | 0.0258 | 2.58 |" in table.value


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_single_member_selection_and_rate_recalculation(account, monkeypatch, environment):
    wb = Workbook()
    ws = wb.active
    ws.title = "直屬會員"
    ws.append(["會員帳號", "遊戲分類", "有效投注", "輸贏金額"])
    ws.append(["Sample_A", "Slots", 100, -10])
    ws.append(["Sample_B", "Slots", 900, -90])
    buf = io.BytesIO()
    wb.save(buf)
    buf.name = "synthetic-members.xlsx"
    monkeypatch.setattr(app_ui.st, "file_uploader", lambda *a, **k: buf)
    at = login(app(account, environment).run())
    at.radio(key="calculation_mode").set_value("單一會員佣金").run()
    assert not at.exception
    assert at.metric[2].value == "2.58"
    assert len(at.dataframe) == 0
    table = next(m for m in at.markdown if m.value.startswith('| 遊戲類型 |'))
    assert not table.proto.allow_html
    assert "| 電子類型 | 100.00 | -10.00 | 0.0258 | 2.58 |" in table.value
    assert at.text_input(key="ratio").value == "0.8"
    at.text_input(key="rate_電子類型").set_value("0.03").run()
    assert at.metric[2].value == "3.00"
    next(s for s in at.radio if s.label in ("會員帳號", "代理帳號")).set_value("sample_b").run()
    assert at.metric[2].value == "27.00"
    assert len(at.get("download_button")) == 1
    assert not any(s.value == "我的歷史報表紀錄" for s in at.subheader)
    prod = login(app(account).run())
    assert not prod.exception
    assert prod.radio(key="calculation_mode").options == ["整體代理結算", "單一會員佣金", "單一下線代理佣金"]


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_agent_mode_switch_and_recalculate(account, monkeypatch, environment):
    wb=Workbook();ws=wb.active;ws.title='下線代理'
    ws.append(['代理帳號','遊戲分類','有效投注','輸贏金額'])
    ws.append(['Sample_A','Slots',100,-10])
    ws.append(['Sample_B','Slots',900,-90])
    m=wb.create_sheet('直屬會員')
    m.append(['會員帳號','遊戲分類','有效投注','輸贏金額'])
    m.append(['Sample_A','Slots',1000,-100])
    buf=io.BytesIO();wb.save(buf);buf.name='synthetic-agents.xlsx'
    monkeypatch.setattr(app_ui.st,'file_uploader',lambda *a,**k:buf)
    at=login(app(account,environment).run())
    at.radio(key='calculation_mode').set_value('單一下線代理佣金').run()
    assert not at.exception
    assert next(s for s in at.radio if s.label in ("會員帳號", "代理帳號")).label=='代理帳號'
    assert at.metric[2].label=='代理總佣金'
    assert at.metric[2].value=='2.58'
    next(s for s in at.radio if s.label in ("會員帳號", "代理帳號")).set_value('sample_b').run()
    assert at.metric[2].value=='23.22'
    at.text_input(key='rate_電子類型').set_value('0.03').run()
    assert at.metric[2].value=='27.00'
    at.radio(key='calculation_mode').set_value('單一會員佣金').run()
    assert next(s for s in at.radio if s.label in ("會員帳號", "代理帳號")).label=='會員帳號'
    assert at.metric[2].value=='30.00'
    at.radio(key='calculation_mode').set_value('單一下線代理佣金').run()
    assert at.metric[2].label=='代理總佣金'
    assert at.metric[2].value=='3.00'


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_sports_and_ratio_are_editable_in_all_three_modes(account, monkeypatch, tmp_path, environment):
    from test_sports_settlement import sports_report
    buf=io.BytesIO(sports_report());buf.name='synthetic-sports.xlsx'
    monkeypatch.setattr(app_ui.st,'file_uploader',lambda *a,**k:buf)
    at=login(app(account,environment).run())
    assert at.text_input(key='rate_Sports').value=='0'
    assert at.text_input(key='rate_Sports').label=='體育 倍率'
    assert any('體育目前倍率為 0' in w.value for w in at.warning)
    at.text_input(key='rate_Sports').set_value('0.01')
    at.text_input(key='ratio').set_value('0.5').run()
    for mode, expected in [('整體代理結算','31.37'),('單一會員佣金','-29.92'),('單一下線代理佣金','-48.71')]:
        at.radio(key='calculation_mode').set_value(mode).run()
        assert not at.exception
        assert at.text_input(key='ratio').value=='0.5'
        assert next(m.value for m in at.metric if m.label=='最終結算')==expected
        at.text_input(key='ratio').set_value('0').run()
        assert next(m.value for m in at.metric if m.label=='最終結算')=='0.00'
        at.text_input(key='ratio').set_value('0.5').run()
    next(b for b in at.button if b.label=='儲存設定').click().run()
    stored=load_settings(account_data_dir(tmp_path,environment,account)/'settings.json')
    assert stored['rates']['Sports']=='0.01' and stored['settlement_ratio']=='0.5'
    at.button(key='logout').click().run()
    login(at)
    assert at.text_input(key='rate_Sports').value=='0.01'
    assert at.text_input(key='ratio').value=='0.5'


@pytest.mark.parametrize("environment,prefix", [("production", "正式使用_"), ("staging", "內部測試_")])
def test_single_account_download_identifies_environment(account, monkeypatch, environment, prefix):
    from test_sports_settlement import sports_report
    buf=io.BytesIO(sports_report());buf.name='synthetic.xlsx'
    filenames=[]
    monkeypatch.setattr(app_ui.st,'file_uploader',lambda *a,**k:buf)
    monkeypatch.setattr(app_ui.st,'download_button',lambda *a,**k:filenames.append(k['file_name']))
    at=login(app(account,environment).run())
    for mode in ['單一會員佣金','單一下線代理佣金']:
        at.radio(key='calculation_mode').set_value(mode).run()
        assert not at.exception
        assert filenames[-1].startswith(prefix)
    if environment=='production':
        assert not any('內部測試環境' in warning.value for warning in at.warning)


def test_account_search_and_missing_account_clear_results(account,monkeypatch):
    from test_sports_settlement import sports_report
    buf=io.BytesIO(sports_report());buf.name='synthetic-search.xlsx'
    monkeypatch.setattr(app_ui.st,'file_uploader',lambda *a,**k:buf)
    at=login(app(account,'staging').run())
    at.radio(key='calculation_mode').set_value('單一會員佣金').run()
    assert len(at.selectbox)==0
    search=next(t for t in at.text_input if t.label=='搜尋會員帳號')
    search.set_value('MEMBER_B').run()
    picker=next(r for r in at.radio if r.label=='會員帳號')
    assert picker.options==['Member_B']
    assert at.metric[0].value=='2,000.00'
    next(t for t in at.text_input if t.label=='搜尋會員帳號').set_value('no-such-account').run()
    assert any('找不到符合' in w.value for w in at.warning)
    assert len(at.metric)==0 and len(at.get('download_button'))==0
    next(t for t in at.text_input if t.label=='搜尋會員帳號').set_value('').run()
    assert len(next(r for r in at.radio if r.label=='會員帳號').options)==2
    at.radio(key='calculation_mode').set_value('單一下線代理佣金').run()
    assert len(at.selectbox)==0
    assert next(r for r in at.radio if r.label=='代理帳號').options==['Agent_A']


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_compatible_upload_computes_all_modes_and_logout_clears_file(account, monkeypatch, environment):
    import base64
    import mobile_upload
    from test_sports_settlement import sports_report
    data = sports_report()
    value = {"name": "synthetic.xlsx", "size": len(data), "data": base64.b64encode(data).decode()}
    monkeypatch.setattr(mobile_upload, "_upload_component", lambda **kwargs: value)
    at = login(app(account, environment).run())
    at.checkbox(key="compatible_upload").check().run()
    assert not at.exception and len(at.get("file_uploader")) == 0
    assert next(m.value for m in at.metric if m.label == '最終結算') == '22.19'
    nonce = at.session_state['compatible_upload_nonce']
    for mode, amount in [('單一會員佣金', '-51.87'), ('單一下線代理佣金', '-85.94')]:
        at.radio(key='calculation_mode').set_value(mode).run()
        assert not at.exception
        assert next(m.value for m in at.metric if m.label == '最終結算') == amount
        assert len(at.get('download_button')) == 1
    value = None
    at.run()
    assert len(at.metric) == 0 and len(at.get('download_button')) == 0
    value = {'name': 'bad.xlsx', 'size': 1, 'data': '!!!'}
    at.run()
    assert at.error and len(at.metric) == 0
    at.button(key='logout').click().run()
    assert 'compatible_upload_nonce' not in at.session_state
    assert len(at.metric) == 0
    login(at)
    at.checkbox(key="compatible_upload").check().run()
    assert at.session_state['compatible_upload_nonce'] != nonce
