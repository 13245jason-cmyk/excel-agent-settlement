from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from settlement import DEFAULT_RATES, calculate_settlement, parse_report


def make_report():
    wb = Workbook()
    ws = wb.active
    ws.title = "總結"
    ws.append(["遊戲分類", "輸贏金額", "有效投注"])
    ws.append(["Slots", -10, 100])
    ws.append(["MiniGame", 20, 200])
    ws.append(["LiveCasino1", -30, 300])
    ws.append(["LiveCasino2", 40, 400])
    ws.append(["總計", 20, 1000])
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def test_parse_and_calculate_direction():
    report = parse_report(BytesIO(make_report()))
    result = calculate_settlement(report, DEFAULT_RATES, Decimal("0.8"))
    assert report["total_win_loss"] == Decimal("20")
    assert result["total_commission"] == Decimal("13.84")
    assert result["net_settlement"] == Decimal("33.84")
    assert result["final_settlement"] == Decimal("27.072")
    assert result["final_settlement"] > 0


def test_missing_required_column_is_explicit_error():
    wb = Workbook()
    ws = wb.active
    ws.title = "總結"
    ws.append(["遊戲分類", "輸贏金額"])
    output = BytesIO()
    wb.save(output)
    try:
        parse_report(BytesIO(output.getvalue()))
    except Exception as exc:
        assert "缺少必要欄位" in str(exc)
    else:
        raise AssertionError("expected an explicit parse error")

