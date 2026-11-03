from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

from member_commission import parse_member_accounts, calculate_member_commission, export_member_commission
from settlement import DEFAULT_RATES, SettlementError


def report(rows=None, merged=False):
    wb=Workbook();ws=wb.active;ws.title='直屬會員'
    ws.append(['會員帳號','遊戲分類','投注金額','有效投注','輸贏金額'])
    for row in rows or [
        ['Sample_A','Slots',999,100,-10],['sample_a','MiniGame',999,200,-20],
        ['Sample_A','LiveCasino2',999,400,-40],['Sample_A 小計',None,999,700,-70],
        ['Sample_B','Slots',999,900,-90],
    ]:
        ws.append(row)
        if isinstance(row[0], str):
            ws.cell(ws.max_row, 1).data_type = "s"
    if merged:ws.merge_cells('A2:A3')
    b=BytesIO();wb.save(b);b.seek(0);return b


def test_single_member_case_aliases_no_subtotals_or_other_accounts():
    members=parse_member_accounts(report())
    r=calculate_member_commission(members,'SAMPLE_A',DEFAULT_RATES)
    assert set(r['games']) == {'Slots','MiniGame','Casino2'}
    assert r['total_valid_bet'] == Decimal('700')
    assert r['total_win_loss'] == Decimal('-70')
    assert r['total_commission'] == Decimal('10.54')
    assert r['games']['Slots']['valid_bet'] == Decimal('100')
    assert calculate_member_commission(members,'sample_b',DEFAULT_RATES)['total_commission'] == Decimal('23.22')


def test_changed_rates_and_repeated_game_rows():
    members=parse_member_accounts(report([['a','Slots',999,100,-10],['A','Slots',999,200,-20]]))
    assert calculate_member_commission(members,'a',DEFAULT_RATES|{'Slots':Decimal('.03')})['total_commission'] == Decimal('9')


def test_merged_member_account():
    members=parse_member_accounts(report([['a','Slots',999,100,-10],['a','MiniGame',999,200,-20]],True))
    assert calculate_member_commission(members,'a',DEFAULT_RATES)['total_valid_bet'] == Decimal('300')


@pytest.mark.parametrize('bad',[None,'NaN','Infinity','1,2','10%',-1])
def test_selected_member_invalid_amount_rejected(bad):
    members=parse_member_accounts(report([['a','Slots',100,bad,0]]))
    with pytest.raises(SettlementError):calculate_member_commission(members,'a',DEFAULT_RATES)


def test_other_member_bad_value_does_not_pollute_selection():
    members=parse_member_accounts(report([['a','Slots',100,100,0],['b','Slots',100,'bad',0]]))
    assert calculate_member_commission(members,'a',DEFAULT_RATES)['total_commission']==Decimal('2.58')
    with pytest.raises(SettlementError):calculate_member_commission(members,'b',DEFAULT_RATES)


def test_required_columns_and_unknown_member():
    with pytest.raises(SettlementError):parse_member_accounts(BytesIO(b'not excel'))
    members=parse_member_accounts(report())
    with pytest.raises(SettlementError):calculate_member_commission(members,'missing',DEFAULT_RATES)
    with pytest.raises(SettlementError):parse_member_accounts(report([[None,'Slots',100,100,0]]))


def test_export_scope_exact_values_and_formula_safety():
    members=parse_member_accounts(report([['=1+1','Slots',100,100,-10]]))
    r=calculate_member_commission(members,'=1+1',DEFAULT_RATES)
    wb=load_workbook(BytesIO(export_member_commission('=unsafe.xlsx',r)))
    ws=wb.active
    assert ws['B3'].data_type == 's'
    assert ws['B4'].value == '=1+1' and ws['B4'].data_type=='s'
    assert ('總佣金（未捨入）','2.5800',None,None,None) in list(ws.values)
