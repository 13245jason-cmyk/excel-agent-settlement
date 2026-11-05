"""Synthetic regression data only; original financial reports must stay outside Git."""
import json
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

import app_ui
from access import account_data_dir
from authentication import Account, hash_password
from member_commission import (calculate_agent_commission, calculate_member_commission,
                               export_member_commission, parse_agent_accounts, parse_member_accounts)
from settlement import (DEFAULT_RATES, ELECTRONIC_GAME, ELECTRONIC_RATES, SettlementError,
                        calculate_settlement, export_result_xlsx, load_settings, parse_report, save_settings)


def workbook(agent_rows=None, member_rows=None):
    wb = Workbook()
    agent = wb.active
    agent.title = '下線代理'
    agent.append(['合成測試報表'])
    # Deliberately move the required columns and header row.
    agent.append(['輸贏金額', '有效投注', '遊戲分類', '代理帳號'])
    for row in agent_rows if agent_rows is not None else [
        [-10, 100, 'Slots', 'Agent_A'], [-5, 50, 'MiniGame', 'Agent_A'],
        [-2.5, 25, ' Fishing ', 'Agent_A'], [-20, 200, 'LiveCasino1', 'Agent_A'],
        [-30, 300, 'Sports', 'Agent_A'], [4, 40, 'FISHING', 'Agent_B'],
        [99999, 99999, '小計', '合計'],
    ]:
        agent.append(row)
    member = wb.create_sheet('直屬會員')
    member.append(['輸贏金額', '有效投注', '遊戲分類', '會員帳號'])
    for row in member_rows if member_rows is not None else [
        [-6, 60, 'Slots', 'Member_A'], [-1.5, 15, 'fishing', 'Member_A'],
        [-2, 20, 'MiniGame', 'Member_A'], [-8, 80, 'LiveCasino2', 'Member_A'],
        [1, 10, 'MiniGame', 'Member_B'], [99999, 99999, '小計', '合計'],
    ]:
        member.append(row)
    output = BytesIO()
    wb.save(output)
    wb.close()
    return output.getvalue()


def results(data, rate='.03', ratio='.8'):
    rates = ELECTRONIC_RATES | {ELECTRONIC_GAME: Decimal(rate)}
    return [
        calculate_settlement(parse_report(BytesIO(data)), rates, Decimal(ratio)),
        calculate_member_commission(parse_member_accounts(BytesIO(data)), 'member_a', rates, Decimal(ratio)),
        calculate_agent_commission(parse_agent_accounts(BytesIO(data)), 'agent_a', rates, Decimal(ratio)),
    ]


def test_fishing_is_grouped_with_slots_and_minigame_in_all_three_modes():
    whole, member, agent = results(workbook())
    assert set(whole['games']) == {ELECTRONIC_GAME, 'Casino1', 'Casino2', 'Sports'}
    assert whole['games'][ELECTRONIC_GAME]['valid_bet'] == Decimal(320)
    assert whole['games'][ELECTRONIC_GAME]['win_loss'] == Decimal(-22)
    assert whole['games'][ELECTRONIC_GAME]['commission'] == Decimal('9.60')
    assert whole['total_win_loss'] == Decimal(-80)
    assert whole['total_commission'] == Decimal('12.36')
    assert whole['final_settlement'] == Decimal('-54.112')
    assert member['games'][ELECTRONIC_GAME]['valid_bet'] == Decimal(95)
    assert member['total_commission'] == Decimal('3.41')
    assert member['final_settlement'] == Decimal('-11.272')
    assert member['direction'] == '會員需交上線'
    assert agent['games'][ELECTRONIC_GAME]['valid_bet'] == Decimal(175)
    assert agent['total_commission'] == Decimal('7.45')
    assert agent['final_settlement'] == Decimal('-48.04')
    assert agent['direction'] == '代理需交上線'


def test_individual_account_results_reconcile_with_whole_report():
    data = workbook()
    rates = ELECTRONIC_RATES
    total = calculate_settlement(parse_report(BytesIO(data)), rates, Decimal('.8'))
    accounts = []
    for parser, calculate in [(parse_member_accounts, calculate_member_commission), (parse_agent_accounts, calculate_agent_commission)]:
        parsed = parser(BytesIO(data))
        accounts.extend(calculate(parsed, key, rates) for key in parsed)
    for key in ['total_commission', 'total_win_loss', 'net_settlement', 'final_settlement']:
        assert sum((a[key] for a in accounts), Decimal(0)) == total[key]


def test_single_shared_rate_and_ratio_recalculate_all_modes():
    original = results(workbook())
    changed = results(workbook(), '.04', '.5')
    for old, new in zip(original, changed):
        assert new['games'][ELECTRONIC_GAME]['commission'] == new['games'][ELECTRONIC_GAME]['valid_bet'] * Decimal('.04')
        assert new['total_win_loss'] == old['total_win_loss']
        assert new['final_settlement'] == new['net_settlement'] * Decimal('.5')


@pytest.mark.parametrize('game', ['Fishing', 'Slots', 'MiniGame', 'Sports'])
def test_absent_games_are_not_added_and_fishing_only_is_valid(game):
    data = workbook([[1, 10, game, 'Agent_A']], [[1, 10, game, 'Member_A']])
    category = ELECTRONIC_GAME if game != 'Sports' else 'Sports'
    for result in results(data):
        assert set(result['games']) == {category}
        assert result['games'][category]['valid_bet'] in (Decimal(10), Decimal(20))


@pytest.mark.parametrize('bad_value', [None, 'not-a-number', 'NaN', 'Infinity'])
@pytest.mark.parametrize('column', [0, 1])
def test_invalid_fishing_values_never_become_zero(bad_value, column):
    row = [-1, 10, 'Fishing', 'Member_A']
    row[column] = bad_value
    data = workbook([row[:3] + ['Agent_A']], [row])
    with pytest.raises(SettlementError):
        parse_report(BytesIO(data))
    for parser, calculate, key in [(parse_member_accounts, calculate_member_commission, 'member_a'),
                                    (parse_agent_accounts, calculate_agent_commission, 'agent_a')]:
        with pytest.raises(SettlementError):
            calculate(parser(BytesIO(data)), key, ELECTRONIC_RATES)


def test_grouping_does_not_mutate_cached_raw_report_or_legacy_limited_mode():
    data = workbook()
    report = parse_report(BytesIO(data))
    before = json.dumps(report, default=str, sort_keys=True)
    grouped = calculate_settlement(report, ELECTRONIC_RATES, Decimal('.8'))
    legacy = calculate_settlement(report, DEFAULT_RATES | {'Fishing': Decimal('.0258')}, Decimal('.8'))
    assert grouped['total_commission'] == legacy['total_commission']
    assert 'Fishing' in legacy['games'] and ELECTRONIC_GAME not in legacy['games']
    assert json.dumps(report, default=str, sort_keys=True) == before


def test_export_uses_grouped_totals_and_shared_rate_in_all_modes():
    whole, member, agent = results(workbook())
    for index, (output, bet, commission, casino_label, casino_bet, casino_commission) in enumerate([
        (export_result_xlsx({}, whole), '320', '9.60', '真人一館', '200', '2.200'),
        (export_member_commission('synthetic.xlsx', member), '95', '2.85', '真人二館', '80', '0.560'),
        (export_member_commission('synthetic.xlsx', agent), '175', '5.25', '真人一館', '200', '2.200'),
    ]):
        wb = load_workbook(BytesIO(output))
        rows = list(wb.active.values)
        row = next(row for row in rows if row[0] == ELECTRONIC_GAME)
        assert row[1] == bet and row[-1] == commission
        assert not any(row[0] in ('Slots', 'MiniGame', 'Fishing') for row in rows)
        casino = next(row for row in rows if row[0] == casino_label)
        assert casino[1] == casino_bet and casino[-1] == casino_commission
        assert not any(row[0] in ('Casino1', 'Casino2') for row in rows)
        assert not any(row[0] == 'Sports' for row in rows)
        if index in (0, 2):  # Whole report and agent fixture both contain Sports.
            assert any(row[0] == '體育' and row[1] == '300' and Decimal(row[-1]) == 0 for row in rows)
        wb.close()


def test_legacy_settings_migrate_preserving_custom_rate_ratio_and_other_games(tmp_path):
    path = tmp_path / 'settings.json'
    legacy = DEFAULT_RATES | {'Slots': Decimal('.03'), 'MiniGame': Decimal('.03'), 'Sports': Decimal('.02')}
    save_settings(path, legacy, Decimal('.65'))
    before = path.read_bytes()
    settings = load_settings(path, group_electronic=True)
    assert settings['rates'][ELECTRONIC_GAME] == '0.03'
    assert settings['rates']['Sports'] == '0.02' and settings['settlement_ratio'] == '0.65'
    assert set(settings['rates']) == set(ELECTRONIC_RATES)
    assert 'migration_notice' not in settings and path.read_bytes() == before
    save_settings(path, ELECTRONIC_RATES | {ELECTRONIC_GAME: Decimal('.045')}, Decimal('.6'))
    reloaded = load_settings(path, group_electronic=True)
    assert reloaded['rates'][ELECTRONIC_GAME] == '0.045' and reloaded['settlement_ratio'] == '0.6'
    assert set(reloaded['rates']) == set(ELECTRONIC_RATES)


def test_conflicting_legacy_rates_show_notice_without_silent_averaging(tmp_path):
    path = tmp_path / 'settings.json'
    save_settings(path, DEFAULT_RATES | {'Slots': Decimal('.03'), 'MiniGame': Decimal('.04')}, Decimal('.8'))
    settings = load_settings(path, group_electronic=True)
    assert settings['rates'][ELECTRONIC_GAME] == '0.03'
    assert '0.03' in settings['migration_notice'] and '0.04' in settings['migration_notice']


def test_empty_report_does_not_create_an_electronic_row():
    result = calculate_settlement(parse_report(BytesIO(workbook([[0, 0, '總計', '合計']], []))), ELECTRONIC_RATES, Decimal('.8'))
    assert result['games'] == {} and result['final_settlement'] == 0


def test_grouped_rate_and_settings_work_end_to_end_on_testing_entry(monkeypatch, tmp_path):
    from test_access_ui import app, login, PASSWORD
    account = Account('ui_owner', '合成測試帳號', hash_password(PASSWORD), ('staging',))
    uploaded = BytesIO(workbook())
    uploaded.name = 'synthetic-fishing.xlsx'
    monkeypatch.setattr(app_ui, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(app_ui, 'upload_report', lambda: uploaded)
    at = login(app(account, 'staging').run())
    assert not at.exception
    assert any(c.value == '版本：report-checks-v1' for c in at.caption)
    assert at.text_input(key='rate_電子類型').value == '0.0258'
    assert at.text_input(key='rate_Casino1').label == '真人一館 倍率'
    assert at.text_input(key='rate_Casino2').label == '真人二館 倍率'
    assert at.text_input(key='rate_Casino1').value == '0.011'
    assert at.text_input(key='rate_Casino2').value == '0.007'
    assert at.text_input(key='rate_Sports').label == '體育 倍率'
    assert not any(t.label in ('Slots 倍率', 'MiniGame 倍率', 'Fishing 倍率') for t in at.text_input)
    at.text_input(key='rate_電子類型').set_value('.03').run()
    for mode, expected in [('整體代理結算', '-54.11'), ('單一會員佣金', '-11.27'), ('單一下線代理佣金', '-48.04')]:
        at.radio(key='calculation_mode').set_value(mode).run()
        assert not at.exception
        assert next(m.value for m in at.metric if m.label == '最終結算') == expected
        table = next(m.value for m in at.markdown if m.value.startswith('| 遊戲類型 |'))
        assert '| 電子類型 |' in table and '| Fishing |' not in table
        assert len(at.get('download_button')) == 1
    next(b for b in at.button if b.label == '儲存設定').click().run()
    stored = load_settings(account_data_dir(tmp_path, 'staging', account) / 'settings.json', group_electronic=True)
    assert stored['rates'][ELECTRONIC_GAME] == '0.03'
    assert stored['rates']['Casino1'] == '0.011' and stored['rates']['Casino2'] == '0.007'
    at.button(key='logout').click().run()
    login(at)
    assert at.text_input(key='rate_電子類型').value == '0.03'
