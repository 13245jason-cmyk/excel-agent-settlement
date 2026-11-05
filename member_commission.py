"""Direct-member commission calculation, separate from agent settlement."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext
from io import BytesIO

from openpyxl import Workbook, load_workbook
from display_tables import game_label
from report_validation import amount, norm, find_header, is_total, game_amounts
from settlement import SettlementError, _game, DEFAULT_SETTLEMENT_RATIO, commission_games


def parse_member_accounts(source, *, sheet_name="直屬會員", account_label="會員"):
    try:
        wb = load_workbook(source, data_only=True)
    except Exception as exc:
        raise SettlementError(f"無法讀取{account_label}報表，請確認是有效且未加密的 .xlsx") from exc
    try:
        sheets = [s for s in wb if norm(s.title) == norm(sheet_name)]
        if len(sheets) != 1:
            raise SettlementError(f"找不到唯一的「{sheet_name}」工作表")
        ws = sheets[0]
        header, columns = find_header(ws, account_label=account_label)
        merged_accounts = {}
        for merged in ws.merged_cells.ranges:
            if merged.min_col == merged.max_col == columns['account']:
                value = ws.cell(merged.min_row, merged.min_col).value
                for ri in range(merged.min_row, merged.max_row+1):
                    merged_accounts[ri] = value
        members = {}
        for row in ws.iter_rows(min_row=header+1):
            ri = row[0].row
            raw_account = row[columns['account']-1].value
            if raw_account is None:
                raw_account = merged_accounts.get(ri)
            account = str(raw_account or '').strip()
            game = row[columns['game']-1].value
            if is_total(game, account):
                continue
            if not norm(game) and all(row[columns[k]-1].value in (None, '') for k in ('valid_bet', 'win_loss')):
                continue
            if not account:
                raise SettlementError(f"{sheet_name}第 {ri} 列缺少{account_label}帳號，無法歸屬遊戲資料")
            key = account.casefold()
            member = members.setdefault(key, {'account': account, 'source_sheet': sheet_name, 'rows': []})
            member['rows'].append({'game': game, 'valid_bet': row[columns['valid_bet']-1].value,
                                   'win_loss': row[columns['win_loss']-1].value, 'row': ri})
        if not members:
            raise SettlementError(f"{sheet_name}沒有可選擇的{account_label}遊戲明細")
        return members
    finally:
        wb.close()


def calculate_member_commission(members, account, rates, ratio=DEFAULT_SETTLEMENT_RATIO, *, account_label="會員"):
    member = members.get(account.strip().casefold())
    if member is None:
        raise SettlementError(f"找不到所選{account_label}帳號")
    ratio = amount(ratio, "結算比例")
    if not 0 <= ratio <= 1:
        raise SettlementError("結算比例必須介於 0 與 1")
    with localcontext() as context:
        context.prec = 80
        games = {}
        for row in member['rows']:
            game, bet, win = game_amounts(row['game'], row['valid_bet'], row['win_loss'],
                                          sheet=member.get('source_sheet', '直屬會員'), row=row['row'], game_resolver=_game)
            item = games.setdefault(game, {'valid_bet': Decimal(0), 'win_loss': Decimal(0)})
            item['valid_bet'] += bet
            item['win_loss'] += win
        games = commission_games(games, rates)
        for game,item in games.items():
            rate = amount(rates.get(game), f'{game_label(game)} 倍率')
            if not 0 <= rate <= 1:
                raise SettlementError(f'{game_label(game)} 倍率必須介於 0 與 1')
            item['rate'] = rate
            item['commission'] = item['valid_bet'] * rate
        total_commission = sum((g['commission'] for g in games.values()), Decimal(0))
        total_win_loss = sum((g['win_loss'] for g in games.values()), Decimal(0))
        net = total_win_loss + total_commission
        final = net * ratio
        return {'account': member['account'], 'source_sheet': member.get('source_sheet', '直屬會員'),
                'account_label': account_label, 'games': games,
                'total_valid_bet': sum((g['valid_bet'] for g in games.values()), Decimal(0)),
                'total_win_loss': total_win_loss, 'total_commission': total_commission,
                'net_settlement': net, 'settlement_ratio': ratio, 'final_settlement': final,
                'direction': f'{account_label}需交上線' if final < 0 else f'上線需給{account_label}' if final > 0 else '雙方無需付款'}


def export_member_commission(filename, result):
    wb = Workbook()
    ws = wb.active
    label = result.get('account_label', '會員')
    ws.title = f'{label}佣金'
    ws.append(['計算類型', f'單一{label}佣金與結算'])
    ws.append(['來源工作表', result.get('source_sheet', '直屬會員')])
    ws.append(['原始報表', filename])
    ws.append([f'{label}帳號', result['account']])
    ws.append(['遊戲類型', '有效投注', '輸贏金額', '佣金倍率', '佣金（未捨入）'])
    for game,item in result['games'].items():
        ws.append([game_label(game), str(item['valid_bet']), str(item['win_loss']), str(item['rate']), str(item['commission'])])
    ws.append(['有效投注合計', str(result['total_valid_bet'])])
    ws.append(['輸贏合計（參考）', str(result['total_win_loss'])])
    ws.append(['總佣金（未捨入）', str(result['total_commission'])])
    ws.append(['總佣金（顯示）', str(result['total_commission'].quantize(Decimal('.01'), rounding='ROUND_HALF_UP'))])
    ws.append(['結算淨額', str(result['net_settlement'])])
    ws.append(['結算比例', str(result['settlement_ratio'])])
    ws.append(['最終結算（未捨入）', str(result['final_settlement'])])
    ws.append(['付款方向', result['direction']])
    ws.append(['最終應付金額', str(abs(result['final_settlement']).quantize(Decimal('.01'), rounding='ROUND_HALF_UP'))])
    ws.append(['計算公式', f"({result['total_win_loss']} + {result['total_commission']}) × {result['settlement_ratio']} = {result['final_settlement']}"])
    for row in ws:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = 's'  # Account/file names must never become Excel formulas.
    for col in 'ABCDE':
        ws.column_dimensions[col].width = 30
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def parse_agent_accounts(source):
    return parse_member_accounts(source, sheet_name="下線代理", account_label="代理")


def calculate_agent_commission(agents, account, rates, ratio=DEFAULT_SETTLEMENT_RATIO):
    return calculate_member_commission(agents, account, rates, ratio, account_label="代理")


def export_agent_commission(filename, result):
    return export_member_commission(filename, result)
