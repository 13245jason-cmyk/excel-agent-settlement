"""Shared, strict validation for all settlement scopes (no spreadsheet imports)."""
import re
from decimal import Decimal, InvalidOperation


class SettlementError(Exception):
    pass


def norm(value):
    return '' if value is None else re.sub(r'\s+', '', str(value)).casefold()


def amount(value, label):
    if isinstance(value, bool) or value is None or str(value).strip() == '':
        raise SettlementError(f'{label}：缺少合法數值')
    text = str(value).strip()
    if not isinstance(value, (Decimal, int, float)) and not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', text):
        raise SettlementError(f'{label}：數值格式錯誤（不可使用百分比、NaN 或無限大）')
    try:
        result = Decimal(text.replace(',', ''))
    except InvalidOperation as exc:
        raise SettlementError(f'{label}：數值格式錯誤') from exc
    if not result.is_finite() or len(result.as_tuple().digits) > 25 or abs(result) > Decimal('1e15'):
        raise SettlementError(f'{label}：數值超出範圍')
    return result


def find_header(ws, *, account_label=None):
    if ws.max_row > 100000 or ws.max_column > 500:
        raise SettlementError(f'「{ws.title}」報表過大（最多 100000 列、500 欄）')
    aliases = {'game': {'遊戲分類', '遊戲類型'}, 'valid_bet': {'有效投注', '有效投注額'}, 'win_loss': {'輸贏金額'}}
    if account_label:
        aliases['account'] = ({'代理帳號', '代理賬號', '代理帳戶', '帳號', 'agentaccount'} if account_label == '代理'
                              else {'會員帳號', '會員賬號', '會員帳戶', '帳號', 'memberaccount'})
    headers = []
    for row_number, row in enumerate(ws.iter_rows(), 1):
        found = {key: [cell.column for cell in row if norm(cell.value) in names] for key, names in aliases.items()}
        if all(found.values()):
            if any(len(hits) != 1 for hits in found.values()):
                raise SettlementError(f'「{ws.title}」第 {row_number} 列標題有重複欄位')
            headers.append((row_number, {key: hits[0] for key, hits in found.items()}))
    if len(headers) != 1:
        raise SettlementError(f'「{ws.title}」缺少必要欄位或標題列不唯一：遊戲分類、有效投注、輸贏金額' +
                              (f'、{account_label}帳號' if account_label else ''))
    return headers[0]


def is_total(*values):
    return any(norm(value).rstrip(':：').endswith(('小計', '合計', '總計')) for value in values)


def game_amounts(raw_game, raw_bet, raw_win, *, sheet, row, game_resolver):
    context = f'「{sheet}」第 {row} 列'
    game = game_resolver(raw_game)
    if not norm(raw_game):
        raise SettlementError(f'{context}欄位「遊戲分類」空白，無法計算此列')
    if game is None:
        raise SettlementError(f'{context}欄位「遊戲分類」為不支援的類型「{str(raw_game)[:80]}」，請確認分類後再計算')
    bet = amount(raw_bet, context + '欄位「有效投注」')
    win = amount(raw_win, context + '欄位「輸贏金額」')
    if bet < 0:
        raise SettlementError(f'{context}欄位「有效投注」不可為負數')
    return game, bet, win
