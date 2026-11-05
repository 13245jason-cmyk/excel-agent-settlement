from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from display_tables import game_label

DEFAULT_RATES = {"Slots": Decimal("0.0258"), "MiniGame": Decimal("0.0258"), "Casino1": Decimal("0.011"), "Casino2": Decimal("0.007"), "Sports": Decimal("0")}
DEFAULT_SETTLEMENT_RATIO = Decimal("0.8")
GAMES = tuple(DEFAULT_RATES)
ELECTRONIC_GAME = "電子類型"
ELECTRONIC_SOURCES = ("Slots", "MiniGame", "Fishing")
ELECTRONIC_RATES = {ELECTRONIC_GAME: DEFAULT_RATES["Slots"], **{k: v for k, v in DEFAULT_RATES.items() if k not in ELECTRONIC_SOURCES}}


class SettlementError(Exception):
    pass


def _norm(value: object) -> str:
    return "" if value is None else str(value).strip().lower().replace(" ", "")


def _decimal(value: object, label: str) -> Decimal:
    if value is None or str(value).strip() == "":
        raise SettlementError(f"欄位「{label}」存在空白數值，請修正報表。")
    try:
        result = Decimal(str(value).replace(",", "").replace("%", ""))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError):
        raise SettlementError(f"欄位「{label}」包含不合法數值：{value}")


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
    for ws in wb.worksheets:
        if _norm(ws.title) == _norm(title):
            return ws
    raise SettlementError(f"找不到「{title}」工作表。")


def parse_report(source: str | Path | BinaryIO) -> dict:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(source, data_only=True, read_only=True)
    except Exception as exc:
        raise SettlementError(f"無法讀取 Excel 檔案：{exc}")
    totals = {}
    found_games = set()
    source_sheets = []
    for sheet_name in ("下線代理", "直屬會員"):
        ws = _find_sheet(wb, sheet_name)
        source_sheets.append(ws.title)
        header_row = None
        columns = {}
        for row in ws.iter_rows():
            found = {_norm(cell.value): cell.column for cell in row if cell.value is not None}
            if "遊戲分類" in found and ("有效投注" in found or "有效投注額" in found) and "輸贏金額" in found:
                header_row = row[0].row
                columns = {"game": found["遊戲分類"], "valid_bet": found.get("有效投注", found.get("有效投注額")), "win_loss": found["輸贏金額"]}
                break
        if not header_row:
            raise SettlementError(f"「{ws.title}」工作表缺少必要欄位：遊戲分類、有效投注、輸贏金額。")
        for row in ws.iter_rows(min_row=header_row + 1):
            game_raw = row[columns["game"] - 1].value
            marker = _norm(game_raw)
            if any(x in marker for x in ("小計", "合計", "總計")):
                continue
            game = _game(game_raw)
            if game is None:
                continue
            valid = _decimal(row[columns["valid_bet"] - 1].value, "有效投注")
            win_loss = _decimal(row[columns["win_loss"] - 1].value, "輸贏金額")
            totals.setdefault(game, {"valid_bet": Decimal("0"), "win_loss": Decimal("0")})
            totals[game]["valid_bet"] += valid
            totals[game]["win_loss"] += win_loss
            found_games.add(game)
    return {"sheet_name": "、".join(source_sheets), "games": totals, "total_win_loss": sum((v["win_loss"] for v in totals.values()), Decimal("0")), "empty_report": not found_games}


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

