from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import streamlit as st

from settlement import (
    DEFAULT_RATES,
    DEFAULT_SETTLEMENT_RATIO,
    SettlementError,
    calculate_settlement,
    export_result_xlsx,
    load_settings,
    parse_report,
    save_history,
    save_settings,
)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "history.json"


def dstr(value: Decimal) -> str:
    return format(value, ",.2f")


def get_settings() -> dict:
    return load_settings(SETTINGS_FILE)


@st.cache_data(show_spinner=False)
def parse_uploaded_report(file_bytes: bytes) -> dict:
    """同一份上傳檔案只解析一次，調整倍率時直接重用結果。"""
    return parse_report(io.BytesIO(file_bytes))


st.set_page_config(page_title="Excel 代理結算系統", page_icon="🧾", layout="wide")
st.title("🧾 Excel 代理結算系統")
st.caption("上傳報表後，系統會從「下線代理」與「直屬會員」分頁加總，並以 Decimal 精準計算。")

settings = get_settings()
with st.sidebar:
    st.header("佣金倍率設定")
    rate_inputs = {}
    for game in DEFAULT_RATES:
        rate_inputs[game] = st.text_input(
            f"{game} 倍率", value=str(settings["rates"].get(game, DEFAULT_RATES[game])), key=f"rate_{game}"
        )
    st.header("結算比例設定")
    ratio_input = st.text_input("結算比例", value=str(settings.get("settlement_ratio", DEFAULT_SETTLEMENT_RATIO)), key="ratio")
    if st.button("儲存設定", use_container_width=True):
        try:
            parsed = {game: Decimal(value.strip()) for game, value in rate_inputs.items()}
            parsed_ratio = Decimal(ratio_input.strip())
            if any(value < 0 for value in parsed.values()) or parsed_ratio < 0:
                raise ValueError("倍率與結算比例不可為負數")
            save_settings(SETTINGS_FILE, parsed, parsed_ratio)
            st.success("設定已儲存，下次載入會沿用。")
        except (InvalidOperation, ValueError):
            st.error("設定必須是合法的非負數字。")

uploaded = st.file_uploader("報表上傳區（.xlsx）", type=["xlsx"])

if uploaded:
    try:
        report = parse_uploaded_report(uploaded.getvalue())
        rates = {game: Decimal(value.strip()) for game, value in rate_inputs.items()}
        ratio = Decimal(ratio_input.strip())
        if any(value < 0 for value in rates.values()) or ratio < 0:
            raise SettlementError("倍率與結算比例不可為負數。")
        result = calculate_settlement(report, rates, ratio)
    except (SettlementError, InvalidOperation, ValueError) as exc:
        st.error(str(exc))
        st.stop()

    st.success(f"已辨識工作表：{report['sheet_name']}；資料期間/代理資訊依原始報表保留。")
    if report.get("empty_report"):
        st.info("此報表的「總計」列為 0，且沒有遊戲明細；系統依原始總計顯示本期無交易資料。")
    elif not report["games"]:
        st.info("報表沒有可計算的遊戲明細，系統依總計列顯示結果。")
    rows = []
    for game, item in result["games"].items():
        rows.append({"遊戲類型": game, "有效投注": dstr(item["valid_bet"]), "佣金倍率": str(item["rate"]), "佣金": dstr(item["commission"])})
    st.subheader("各遊戲有效投注及佣金明細")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總輸贏", dstr(result["total_win_loss"]))
    c2.metric("總佣金", dstr(result["total_commission"]))
    c3.metric("結算淨額", dstr(result["net_settlement"]))
    c4.metric("最終結算", dstr(result["final_settlement"]))

    final = result["final_settlement"]
    if final < 0:
        st.error(f"代理需交上線：{dstr(abs(final))}")
    elif final > 0:
        st.success(f"上線需給代理：{dstr(final)}")
    else:
        st.info("雙方無需付款")

    output = export_result_xlsx(report, result)
    st.download_button("⬇️ 一鍵下載 Excel 結算結果", output, file_name=f"{Path(uploaded.name).stem}_結算結果.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    if st.button("儲存本次歷史報表紀錄", use_container_width=True):
        save_history(HISTORY_FILE, uploaded.name, result)
        st.success("歷史紀錄已儲存。")

st.divider()
st.subheader("歷史報表紀錄")
history = []
if HISTORY_FILE.exists():
    import json
    history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
if history:
    st.dataframe(pd.DataFrame(history), hide_index=True, use_container_width=True)
else:
    st.caption("尚無歷史紀錄。")

