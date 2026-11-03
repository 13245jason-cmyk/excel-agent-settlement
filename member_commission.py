"""Direct-member commission calculation, separate from agent settlement."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext
from io import BytesIO

from openpyxl import Workbook, load_workbook
from settlement import SettlementError, _game


def norm(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def amount(value, label):
    if isinstance(value, bool) or value is None:
        raise SettlementError(f"{label}：缺少合法數值")
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        raise SettlementError(f"{label}：數值格式錯誤")
    try:
        result = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise SettlementError(f"{label}：數值格式錯誤") from exc
    if not result.is_finite() or len(result.as_tuple().digits) > 25 or abs(result) > Decimal('1e15'):
        raise SettlementError(f"{label}：數值超出範圍")
    return result


def parse_member_accounts(source):
    try:
        wb = load_workbook(source, data_only=True)
    except Exception as exc:
        raise SettlementError("無法讀取會員報表，請確認是有效且未加密的 .xlsx") from exc
    try:
        sheets = [s for s in wb if norm(s.title) == "直屬會員"]
        if len(sheets) != 1:
            raise SettlementError("找不到唯一的「直屬會員」工作表")
        ws = sheets[0]
        if ws.max_row > 100000 or ws.max_column > 500:
            raise SettlementError("直屬會員報表過大")
        aliases = {
            "account": {"會員帳號", "會員賬號", "會員帳戶", "帳號", "memberaccount"},
            "game": {"遊戲分類", "遊戲類型"},
            "valid_bet": {"有效投注", "有效投注額"},
            "win_loss": {"輸贏金額"},
        }
        headers = []
        for row in ws.iter_rows():
            found = {key: [c.column for c in row if norm(c.value) in names] for key, names in aliases.items()}
            if all(found.values()):
                if any(len(hits) != 1 for hits in found.values()):
                    raise SettlementError("直屬會員標題有重複欄位")
                headers.append((row[0].row, {k: v[0] for k,v in found.items()}))
        if len(headers) != 1:
            raise SettlementError("直屬會員需要唯一標題列：會員帳號、遊戲分類、有效投注、輸贏金額")
        header, columns = headers[0]
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
            if not norm(game) or any(m in norm(game) or m in norm(account) for m in ('小計','合計','總計')):
                continue
            if not account:
                raise SettlementError(f"直屬會員第 {ri} 列缺少會員帳號，無法歸屬遊戲資料")
            key = account.casefold()
            member = members.setdefault(key, {'account': account, 'rows': []})
            member['rows'].append({'game': game, 'valid_bet': row[columns['valid_bet']-1].value,
                                   'win_loss': row[columns['win_loss']-1].value, 'row': ri})
        if not members:
            raise SettlementError("直屬會員沒有可選擇的會員遊戲明細")
        return members
    finally:
        wb.close()


def calculate_member_commission(members, account, rates):
    member = members.get(account.strip().casefold())
    if member is None:
        raise SettlementError("找不到所選會員帳號")
    with localcontext() as context:
        context.prec = 80
        games = {}
        for row in member['rows']:
            game = _game(norm(row['game']))
            if game is None:
                raise SettlementError(f"所選會員第 {row['row']} 列有不支援的遊戲分類，無法完整計算佣金")
            bet = amount(row['valid_bet'], f"第 {row['row']} 列有效投注")
            win = amount(row['win_loss'], f"第 {row['row']} 列輸贏金額")
            if bet < 0:
                raise SettlementError("有效投注不可為負數")
            item = games.setdefault(game, {'valid_bet': Decimal(0), 'win_loss': Decimal(0)})
            item['valid_bet'] += bet
            item['win_loss'] += win
        for game,item in games.items():
            rate = amount(rates.get(game), f'{game} 倍率')
            if not 0 <= rate <= 1:
                raise SettlementError(f'{game} 倍率必須介於 0 與 1')
            item['rate'] = rate
            item['commission'] = item['valid_bet'] * rate
        return {'account': member['account'], 'games': games,
                'total_valid_bet': sum((g['valid_bet'] for g in games.values()), Decimal(0)),
                'total_win_loss': sum((g['win_loss'] for g in games.values()), Decimal(0)),
                'total_commission': sum((g['commission'] for g in games.values()), Decimal(0))}


def export_member_commission(filename, result):
    wb = Workbook()
    ws = wb.active
    ws.title = '會員佣金'
    ws.append(['計算類型', '單一會員佣金（未套用代理結算比例）'])
    ws.append(['來源工作表', '直屬會員'])
    ws.append(['原始報表', filename])
    ws.append(['會員帳號', result['account']])
    ws.append(['遊戲類型', '有效投注', '輸贏金額', '佣金倍率', '佣金（未捨入）'])
    for game,item in result['games'].items():
        ws.append([game, str(item['valid_bet']), str(item['win_loss']), str(item['rate']), str(item['commission'])])
    ws.append(['有效投注合計', str(result['total_valid_bet'])])
    ws.append(['輸贏合計（參考）', str(result['total_win_loss'])])
    ws.append(['總佣金（未捨入）', str(result['total_commission'])])
    ws.append(['總佣金（顯示）', str(result['total_commission'].quantize(Decimal('.01'), rounding='ROUND_HALF_UP'))])
    for row in ws:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = 's'  # Account/file names must never become Excel formulas.
    for col in 'ABCDE':
        ws.column_dimensions[col].width = 30
    output = BytesIO()
    wb.save(output)
    return output.getvalue()
