from decimal import Decimal
from io import BytesIO
import json
import pytest
from openpyxl import Workbook, load_workbook
from settlement import DEFAULT_RATES, SettlementError, parse_report, calculate_settlement, load_settings, save_settings, export_result_xlsx
from member_commission import parse_member_accounts, parse_agent_accounts, calculate_member_commission, calculate_agent_commission, export_member_commission


def sports_report():
    w=Workbook();a=w.active;a.title='下線代理'
    a.append(['代理帳號','遊戲分類','有效投注','輸贏金額'])
    a.append(['Agent_A','SPORTS',1000,-100]);a.append(['Agent_A','Slots',100,-10])
    m=w.create_sheet('直屬會員');m.append(['會員帳號','遊戲分類','有效投注','輸贏金額'])
    m.append(['Member_A','Sports',500,-50]);m.append(['Member_A','MiniGame',200,-20]);m.append(['Member_B','sports',2000,200])
    b=BytesIO();w.save(b);return b.getvalue()


def results(ratio='0.8'):
    data=sports_report();rates=DEFAULT_RATES|{'Sports':Decimal('.01')}
    whole=calculate_settlement(parse_report(BytesIO(data)),rates,Decimal(ratio))
    member=calculate_member_commission(parse_member_accounts(BytesIO(data)),'member_a',rates,Decimal(ratio))
    agent=calculate_agent_commission(parse_agent_accounts(BytesIO(data)),'agent_a',rates,Decimal(ratio))
    return whole,member,agent


def test_sports_is_included_in_all_three_modes():
    whole,member,agent=results()
    assert whole['games']['Sports']['valid_bet']==Decimal('3500')
    assert whole['total_commission']==Decimal('42.74')
    assert whole['final_settlement']==Decimal('50.192')
    assert member['games']['Sports']['valid_bet']==Decimal('500')
    assert member['total_commission']==Decimal('10.16')
    assert member['net_settlement']==Decimal('-59.84')
    assert member['final_settlement']==Decimal('-47.872')
    assert member['direction']=='會員需交上線'
    assert agent['total_commission']==Decimal('12.58')
    assert agent['final_settlement']==Decimal('-77.936')
    assert agent['direction']=='代理需交上線'


def test_ratio_changes_final_but_not_commissions():
    a=results();b=results('0.5')
    for old,new in zip(a,b):
        assert old['total_commission']==new['total_commission']
        assert new['final_settlement']==new['net_settlement']*Decimal('.5')
    assert b[1]['final_settlement']==Decimal('-29.92')


def test_default_zero_sports_still_includes_win_loss():
    assert DEFAULT_RATES['Sports']==0
    r=calculate_settlement(parse_report(BytesIO(sports_report())),DEFAULT_RATES,Decimal('.8'))
    assert r['total_win_loss']==20
    assert r['games']['Sports']['commission']==0
    assert r['final_settlement']==Decimal('22.192')


def test_positive_and_zero_account_directions():
    data=parse_member_accounts(BytesIO(sports_report()))
    r=calculate_member_commission(data,'member_b',DEFAULT_RATES,Decimal('.8'))
    assert r['final_settlement']==160 and r['direction']=='上線需給會員'
    r=calculate_member_commission(data,'member_b',DEFAULT_RATES,Decimal(0))
    assert r['final_settlement']==0 and r['direction']=='雙方無需付款'


@pytest.mark.parametrize('ratio',['NaN','Infinity','-0.1','1.1'])
def test_invalid_ratio_rejected_in_all_modes(ratio):
    with pytest.raises(SettlementError):results(ratio)
    data=sports_report()
    with pytest.raises(SettlementError):calculate_member_commission(parse_member_accounts(BytesIO(data)),'member_a',DEFAULT_RATES,Decimal(ratio))
    with pytest.raises(SettlementError):calculate_agent_commission(parse_agent_accounts(BytesIO(data)),'agent_a',DEFAULT_RATES,Decimal(ratio))


def test_existing_settings_receive_only_new_sports_default(tmp_path):
    p=tmp_path/'settings.json'
    original={'rates':{k:str(v) for k,v in DEFAULT_RATES.items() if k!='Sports'},'settlement_ratio':'0.7'}
    original['rates']['Slots']='0.03'
    p.write_text(json.dumps(original));before=p.read_bytes()
    loaded=load_settings(p)
    assert loaded['rates']['Sports']=='0' and loaded['rates']['Slots']=='0.03'
    assert loaded['settlement_ratio']=='0.7' and p.read_bytes()==before
    save_settings(p,DEFAULT_RATES|{'Sports':Decimal('.02')},Decimal('.5'))
    assert load_settings(p)['rates']['Sports']=='0.02'
    assert load_settings(p)['settlement_ratio']=='0.5'


def test_export_includes_exact_settlement_and_ratio():
    whole,member,agent=results()
    for r in [member,agent]:
        w=load_workbook(BytesIO(export_member_commission('synthetic.xlsx',r)))
        values=list(w.active.values)
        assert ('結算比例','0.8',None,None,None) in values
        assert ('最終結算（未捨入）',str(r['final_settlement']),None,None,None) in values
        assert ('付款方向',r['direction'],None,None,None) in values
    w=load_workbook(BytesIO(export_result_xlsx({},whole)))
    assert any(row[0]=='最終結算' and row[1]=='50.19200' for row in w.active.values)
