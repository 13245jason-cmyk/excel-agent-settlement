from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

import app_ui
from authentication import Account, hash_password
from member_commission import parse_member_accounts, parse_agent_accounts, calculate_member_commission, calculate_agent_commission
from settlement import ELECTRONIC_RATES, SettlementError, parse_report


def report(game='Slots', bet=100, win=-10, summary=None, total=None):
    wb = Workbook()
    wb.remove(wb.active)
    for sheet, label in [('下線代理', '代理'), ('直屬會員', '會員')]:
        ws = wb.create_sheet(sheet)
        ws.append([f'{label}帳號', '遊戲分類', '有效投注', '輸贏金額'])
        ws.append(['Example_A', game, bet, win])
        if total is not None:
            ws.append(['總計', None, total[0], total[1]])
    if summary is not None:
        ws = wb.create_sheet('總結')
        ws.append(['有效投注', '遊戲分類', '輸贏金額'])
        for game_name, valid, winning in summary:
            ws.append([valid, game_name, winning])
    b = BytesIO()
    wb.save(b)
    wb.close()
    return b.getvalue()


@pytest.mark.parametrize('field', ['bet', 'win'])
@pytest.mark.parametrize('bad', [None, '', True, 'NaN', 'Infinity', '1,2', '10%', 'bad', '1e2'])
def test_same_invalid_money_rules_for_all_three_modes(field, bad):
    data = report(**{field: bad})
    calls = [lambda: parse_report(BytesIO(data)),
             lambda: calculate_member_commission(parse_member_accounts(BytesIO(data)), 'example_a', ELECTRONIC_RATES),
             lambda: calculate_agent_commission(parse_agent_accounts(BytesIO(data)), 'example_a', ELECTRONIC_RATES)]
    for call in calls:
        with pytest.raises(SettlementError, match='第 2 列.*欄位'):
            call()


@pytest.mark.parametrize('game', ['NewGame', None, '', '未知總計遊戲'])
def test_unknown_or_missing_game_never_silently_drops_a_row(game):
    data = report(game=game)
    with pytest.raises(SettlementError, match='遊戲分類'):
        parse_report(BytesIO(data))
    for parser, calc in [(parse_member_accounts, calculate_member_commission), (parse_agent_accounts, calculate_agent_commission)]:
        with pytest.raises(SettlementError, match='遊戲分類'):
            calc(parser(BytesIO(data)), 'example_a', ELECTRONIC_RATES)


def test_negative_valid_bet_is_rejected_in_every_scope():
    data = report(bet=-1)
    with pytest.raises(SettlementError, match='有效投注.*負數'):
        parse_report(BytesIO(data))
    for parser, calc in [(parse_member_accounts, calculate_member_commission), (parse_agent_accounts, calculate_agent_commission)]:
        with pytest.raises(SettlementError, match='有效投注.*負數'):
            calc(parser(BytesIO(data)), 'example_a', ELECTRONIC_RATES)


def test_summary_matches_without_being_added_twice():
    data = report(summary=[('Slots', 200, -20), ('Fishing', 0, 0)], total=(100, -10))
    result = parse_report(BytesIO(data))
    assert result['summary_checked']
    assert result['games']['Slots']['valid_bet'] == 200
    assert result['total_win_loss'] == -20
    assert set(result['games']) == {'Slots'}


@pytest.mark.parametrize('summary', [[('Slots', 201, -20)], [('Slots', 200, -21)], [('Fishing', 200, -20)]])
def test_summary_mismatch_blocks_settlement_with_difference(summary):
    with pytest.raises(SettlementError, match='總結.*核對不符.*差額'):
        parse_report(BytesIO(report(summary=summary)))


def test_summary_tolerance_is_exactly_one_cent():
    assert parse_report(BytesIO(report(summary=[('Slots', 200.01, -20.01)])))['summary_checked']
    with pytest.raises(SettlementError, match='核對不符'):
        parse_report(BytesIO(report(summary=[('Slots', 200.011, -20)])))


def test_missing_summary_is_explicit_and_does_not_require_missing_game_rows():
    parsed = parse_report(BytesIO(report()))
    assert not parsed['summary_checked']
    assert set(parsed['games']) == {'Slots'}


def test_incorrect_source_grand_total_is_not_ignored():
    with pytest.raises(SettlementError, match='明細與總計核對不符'):
        parse_report(BytesIO(report(total=(101, -10))))


def test_empty_report_without_explicit_zero_is_not_assumed_to_be_zero():
    wb = load_workbook(BytesIO(report()))
    for ws in wb:
        ws.delete_rows(2)
    b = BytesIO(); wb.save(b)
    with pytest.raises(SettlementError, match='空報表當作 0'):
        parse_report(BytesIO(b.getvalue()))


def test_summary_game_differences_cannot_cancel_each_other_out():
    wb = load_workbook(BytesIO(report(summary=[('Slots', 101, -11), ('Sports', 99, -9)])))
    wb['直屬會員'].cell(2, 2, 'Sports')
    b = BytesIO(); wb.save(b)
    with pytest.raises(SettlementError, match='核對不符'):
        parse_report(BytesIO(b.getvalue()))


def test_duplicate_headers_and_alias_columns_are_rejected():
    wb = load_workbook(BytesIO(report()))
    ws = wb['下線代理']
    ws.cell(1, 5, '有效投注額')
    ws.cell(2, 5, 100)
    b = BytesIO()
    wb.save(b)
    with pytest.raises(SettlementError, match='重複欄位'):
        parse_report(BytesIO(b.getvalue()))


@pytest.mark.parametrize('mode', ['整體代理結算', '單一會員佣金', '單一下線代理佣金'])
def test_ui_replacement_with_invalid_report_removes_old_results_and_download(monkeypatch, tmp_path, mode):
    from test_access_ui import app, login, PASSWORD
    account = Account('ui_owner', '合成測試', hash_password(PASSWORD), ('staging',))
    current = BytesIO(report())
    current.name = 'same-name.xlsx'
    monkeypatch.setattr(app_ui, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(app_ui, 'upload_report', lambda: current)
    at = login(app(account, 'staging').run())
    at.radio(key='calculation_mode').set_value(mode).run()
    assert not at.exception and at.metric and len(at.get('download_button')) == 1
    current = BytesIO(report(game='Unknown_Game'))
    current.name = 'same-name.xlsx'
    at.run()
    assert not at.exception
    assert any('報表或參數檢查未通過' in e.value and '遊戲分類' in e.value and '第 2 列' in e.value for e in at.error)
    assert len(at.metric) == 0 and len(at.get('download_button')) == 0


def test_ui_summary_mismatch_blocks_download_and_missing_summary_warns(monkeypatch, tmp_path):
    from test_access_ui import app, login, PASSWORD
    account = Account('ui_owner', '合成測試', hash_password(PASSWORD), ('staging',))
    current = BytesIO(report(summary=[('Slots', 201, -20)])); current.name = 'synthetic.xlsx'
    monkeypatch.setattr(app_ui, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(app_ui, 'upload_report', lambda: current)
    at = login(app(account, 'staging').run())
    assert any('核對不符' in e.value for e in at.error) and not at.metric
    assert len(at.get('download_button')) == 0
    current = BytesIO(report()); current.name = 'synthetic.xlsx'
    at.run()
    assert at.metric and any('未提供「總結」' in w.value for w in at.warning)
