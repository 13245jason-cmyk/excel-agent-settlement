from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from display_tables import game_label
from report_validation import SettlementError, norm as _norm, amount as _decimal, find_header, is_total, game_amounts

DEFAULT_RATES = {"Slots": Decimal("0.0258"), "MiniGame": Decimal("0.0258"), "Casino1": Decimal("0.011"), "Casino2": Decimal("0.007"), "Sports": Decimal("0")}
DEFAULT_SETTLEMENT_RATIO = Decimal("0.8")
GAMES = tuple(DEFAULT_RATES)
ELECTRONIC_GAME = "電子類型"
ELECTRONIC_SOURCES = ("Slots", "MiniGame", "Fishing")
ELECTRONIC_RATES = {ELECTRONIC_GAME: DEFAULT_RATES["Slots"], **{k: v for k, v in DEFAULT_RATES.items() if k not in ELECTRONIC_SOURCES}}


def _game(value: object) -> str | None:
    key = _norm(value)
    aliases = {"slots": "Slots", "minigame": "MiniGame", "fishing": "Fishing", "livecasino1": "Casino1", "casino1": "Casino1", "livecasino2": "Casino2", "casino2": "Casino2", "sports": "Sports"}
    return aliases.get(key)


def commission_games(games: dict, rates: dict) -> dict:
    """Group existing electronic rows only when using the combined rate schema.

    Keep the raw parser/cache and the independent limited app's legacy rates intact.
    Callers calculate inside their Decimal precision context; never round components.
    """
    if ELECTRONIC_GAME not in rates:
        return {game: dict(item) for game, item in games.items()}
    grouped = {}
    for game, source in games.items():
        category = ELECTRONIC_GAME if game in ELECTRONIC_SOURCES else game
        item = grouped.setdefault(category, {"valid_bet": Decimal(0), "win_loss": Decimal(0)})
        item["valid_bet"] += source["valid_bet"]
        item["win_loss"] += source["win_loss"]
    return grouped


def _find_sheet(wb, title: str):
    matches = [ws for ws in wb if _norm(ws.title) == _norm(title)]
    if len(matches) > 1:
        raise SettlementError(f'找不到唯一的「{title}」工作表。')
    if matches:
        return matches[0]
    raise SettlementError(f"找不到「{title}」工作表。")


def _sheet_totals(ws, *, evidence=None):
    header, columns = find_header(ws)
    headers = next(ws.iter_rows(min_row=header, max_row=header))
    accounts = [c.column for c in headers if _norm(c.value) in
                {'代理帳號', '代理賬號', '代理帳戶', '會員帳號', '會員賬號', '會員帳戶', '帳號', 'agentaccount', 'memberaccount'}]
    totals, grand_totals = {}, []
    for row_number, row in enumerate(ws.iter_rows(min_row=header + 1), header + 1):
        raw_game = row[columns['game'] - 1].value
        raw_bet = row[columns['valid_bet'] - 1].value
        raw_win = row[columns['win_loss'] - 1].value
        account = row[accounts[0] - 1].value if len(accounts) == 1 else None
        if is_total(raw_game, account):
            if '總計' in (_norm(raw_game).rstrip(':：'), _norm(account).rstrip(':：')):
                context = f'「{ws.title}」第 {row_number} 列總計'
                bet, win = _decimal(raw_bet, context + '有效投注'), _decimal(raw_win, context + '輸贏金額')
                if bet < 0:
                    raise SettlementError(context + '有效投注不可為負數')
                grand_totals.append({'valid_bet': bet, 'win_loss': win})
            continue
        if not _norm(raw_game) and all(v in (None, '') for v in (raw_bet, raw_win)):
            continue
        game, valid, win = game_amounts(raw_game, raw_bet, raw_win, sheet=ws.title, row=row_number, game_resolver=_game)
        item = totals.setdefault(game, {'valid_bet': Decimal(0), 'win_loss': Decimal(0)})
        item['valid_bet'] += valid
        item['win_loss'] += win
    if len(grand_totals) > 1:
        raise SettlementError(f'「{ws.title}」有重複總計列，無法唯一核對')
    if grand_totals:
        actual = {key: sum((v[key] for v in totals.values()), Decimal(0)) for key in ('valid_bet', 'win_loss')}
        _compare_totals(actual, grand_totals[0], f'「{ws.title}」明細與總計')
    if evidence is not None and (totals or grand_totals):
        evidence.append(True)
    return totals


def _compare_totals(actual, expected, context):
    for key, label in [('valid_bet', '有效投注'), ('win_loss', '輸贏金額')]:
        delta = actual[key] - expected[key]
        if abs(delta) > Decimal('0.01'):
            raise SettlementError(f'{context}核對不符：{label}明細 {actual[key]}、報表 {expected[key]}、差額 {delta}（容許 0.01）。請修正後重新上傳')


def parse_report(source: str | Path | BinaryIO) -> dict:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(source, data_only=True, read_only=True)
    except Exception as exc:
        raise SettlementError('無法讀取 Excel 檔案，請確認是有效且未加密的 .xlsx') from exc
    try:
        with localcontext() as context:
            context.prec = 80
            totals, source_sheets, evidence = {}, [], []
            for sheet_name in ('下線代理', '直屬會員'):
                ws = _find_sheet(wb, sheet_name)
                source_sheets.append(ws.title)
                for game, values in _sheet_totals(ws, evidence=evidence).items():
                    item = totals.setdefault(game, {'valid_bet': Decimal(0), 'win_loss': Decimal(0)})
                    for key in item:
                        item[key] += values[key]
            summaries = [ws for ws in wb if _norm(ws.title) == _norm('總結')]
            if len(summaries) > 1:
                raise SettlementError('找不到唯一的「總結」工作表')
            if summaries:
                summary = _sheet_totals(summaries[0], evidence=evidence)
                for game in set(totals) | set(summary):
                    zero = {'valid_bet': Decimal(0), 'win_loss': Decimal(0)}
                    _compare_totals(totals.get(game, zero), summary.get(game, zero), f'「總結」{game_label(game)} 與來源分頁')
            if not evidence:
                raise SettlementError('報表沒有遊戲明細或明確的零金額資料，無法將空報表當作 0 結算。請提供完整報表')
            return {'sheet_name': '、'.join(source_sheets), 'games': totals,
                    'total_win_loss': sum((v['win_loss'] for v in totals.values()), Decimal(0)), 'empty_report': not totals,
                    'summary_checked': bool(summaries)}
    finally:
        wb.close()


def calculate_settlement(report: dict, rates: dict[str, Decimal], ratio: Decimal) -> dict:
    if not ratio.is_finite() or not 0 <= ratio <= 1:
        raise SettlementError("結算比例必須是 0 到 1 之間的有限數字。")
    with localcontext() as context:
        context.prec = 80
        games = {}
        total_commission = Decimal("0")
        for game, source in commission_games(report["games"], rates).items():
            if game not in rates:
                raise SettlementError(f"報表中的遊戲類型「{game_label(game)}」沒有對應佣金倍率設定。")
            rate = rates[game]
            if not rate.is_finite() or not 0 <= rate <= 1:
                raise SettlementError(f"{game_label(game)} 倍率必須是 0 到 1 之間的有限數字。")
            commission = source["valid_bet"] * rate
            games[game] = {**source, "rate": rate, "commission": commission}
            total_commission += commission
        net = report["total_win_loss"] + total_commission
        return {"games": games, "total_win_loss": report["total_win_loss"], "total_commission": total_commission, "net_settlement": net, "settlement_ratio": ratio, "final_settlement": net * ratio}


def _json_default(value):
    return str(value) if isinstance(value, Decimal) else value


def load_settings(path: Path, *, group_electronic: bool = False) -> dict:
    if not path.exists():
        defaults = ELECTRONIC_RATES if group_electronic else DEFAULT_RATES
        return {"rates": {k: str(v) for k, v in defaults.items()}, "settlement_ratio": str(DEFAULT_SETTLEMENT_RATIO)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stored = data["rates"]
        if ELECTRONIC_GAME in stored:
            return {"rates": {k: str(stored.get(k, v) if k == "Sports" else stored[k]) for k, v in ELECTRONIC_RATES.items()}, "settlement_ratio": str(data["settlement_ratio"])}
        legacy = {k: str(stored.get(k, DEFAULT_RATES[k]) if k == "Sports" else stored[k]) for k in GAMES}
        if not group_electronic:
            return {"rates": legacy, "settlement_ratio": str(data["settlement_ratio"])}
        migrated = {ELECTRONIC_GAME: legacy["Slots"], **{k: v for k, v in legacy.items() if k not in ELECTRONIC_SOURCES}}
        result = {"rates": migrated, "settlement_ratio": str(data["settlement_ratio"])}
        if Decimal(legacy["Slots"]) != Decimal(legacy["MiniGame"]):
            result["migration_notice"] = f"舊 Slots 倍率 {legacy['Slots']} 與 MiniGame 倍率 {legacy['MiniGame']} 不同；電子類型先沿用 Slots 倍率，請確認後儲存。"
        return result
    except (OSError, KeyError, TypeError, InvalidOperation, json.JSONDecodeError) as exc:
        raise SettlementError(f"設定檔格式錯誤：{exc}")


def save_settings(path: Path, rates: dict[str, Decimal], ratio: Decimal) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rates": rates, "settlement_ratio": ratio}, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def save_history(path: Path, filename: str, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    history.insert(0, {"時間": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "檔案": filename, "總輸贏": str(result["total_win_loss"]), "總佣金": str(result["total_commission"]), "結算淨額": str(result["net_settlement"]), "最終結算": str(result["final_settlement"]), "結算方向": "代理需交上線" if result["final_settlement"] < 0 else "上線需給代理" if result["final_settlement"] > 0 else "雙方無需付款"})
    path.write_text(json.dumps(history[:100], ensure_ascii=False, indent=2), encoding="utf-8")


def export_result_xlsx(report: dict, result: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "結算結果"
    ws.append(["遊戲類型", "有效投注", "佣金倍率", "佣金"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for game, item in result["games"].items():
        ws.append([game_label(game), str(item["valid_bet"]), str(item["rate"]), str(item["commission"])])
    ws.append([])
    ws.append(["總輸贏", str(result["total_win_loss"])])
    ws.append(["總佣金", str(result["total_commission"])])
    ws.append(["結算淨額", str(result["net_settlement"])])
    ws.append(["結算比例", str(result["settlement_ratio"])])
    ws.append(["最終結算", str(result["final_settlement"])])
    direction = "代理需交上線" if result["final_settlement"] < 0 else "上線需給代理" if result["final_settlement"] > 0 else "雙方無需付款"
    ws.append(["結算方向", direction])
    ws.append(["最終應付金額", str(abs(result["final_settlement"]).quantize(Decimal(".01"), rounding=ROUND_HALF_UP))])
    for row in ws:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    for column in ("B", "D"):
        for cell in ws[column][1:]:
            cell.number_format = '#,##0.00'
    output = BytesIO()
    wb.save(output)
    return output.getvalue()

