from io import BytesIO
from decimal import Decimal
import pytest
from openpyxl import Workbook, load_workbook

from member_commission import parse_agent_accounts, calculate_agent_commission, export_agent_commission, parse_member_accounts, calculate_member_commission
from settlement import DEFAULT_RATES, SettlementError


def report(merged=False, wrong_header=False):
    wb=Workbook();ws=wb.active;ws.title='下線代理'
    ws.append(['說明'])
    ws.append(['輸贏金額','代理帳號' if not wrong_header else '會員帳號','投注金額','遊戲分類','有效投注'])
    ws.append([-10,'Sample_A',999,'Slots',100])
    ws.append([-20,'sample_a',999,'MiniGame',200])
    ws.append([-30,'Sample_A 小計',999,None,300])
    ws.append([-90,'Sample_B',999,'LiveCasino2',900])
    if merged: ws.merge_cells('B3:B4')
    member=wb.create_sheet('直屬會員')
    member.append(['會員帳號','遊戲分類','有效投注','輸贏金額'])
    member.append(['Sample_A','Slots',1000,-100])
    b=BytesIO();wb.save(b);b.seek(0);return b


def test_agent_account_scope_and_correct_columns():
    agents=parse_agent_accounts(report())
    result=calculate_agent_commission(agents,'SAMPLE_A',DEFAULT_RATES)
    assert set(result['games'])=={'Slots','MiniGame'}
    assert result['total_valid_bet']==Decimal('300')
    assert result['total_win_loss']==Decimal('-30')
    assert result['total_commission']==Decimal('7.74')
    assert result['source_sheet']=='下線代理'
    assert result['account_label']=='代理'
    assert calculate_agent_commission(agents,'sample_b',DEFAULT_RATES)['total_commission']==Decimal('6.3')


def test_agent_and_member_same_account_never_mix():
    a=calculate_agent_commission(parse_agent_accounts(report()),'sample_a',DEFAULT_RATES)
    m=calculate_member_commission(parse_member_accounts(report()),'sample_a',DEFAULT_RATES)
    assert a['total_commission']==Decimal('7.74')
    assert m['total_commission']==Decimal('25.8')


def test_merged_agent_and_changed_rate():
    result=calculate_agent_commission(parse_agent_accounts(report(merged=True)),'sample_a',DEFAULT_RATES|{'Slots':Decimal('.03')})
    assert result['total_commission']==Decimal('8.16')


def test_bad_agent_header_rejected():
    with pytest.raises(SettlementError,match='代理帳號'):
        parse_agent_accounts(report(wrong_header=True))


def test_agent_export_identifies_sheet_and_account():
    r=calculate_agent_commission(parse_agent_accounts(report()),'sample_a',DEFAULT_RATES)
    w=load_workbook(BytesIO(export_agent_commission('synthetic.xlsx',r)))
    assert w.active.title=='代理佣金'
    assert w.active['B2'].value=='下線代理'
    assert w.active['A4'].value=='代理帳號'
    assert ('總佣金（顯示）','7.74',None,None,None) in list(w.active.values)
