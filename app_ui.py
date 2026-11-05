from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import hashlib
import json
import re

from access import account_data_dir, require_login
from authentication import ENVIRONMENTS
from display_tables import table_markdown, game_label

import streamlit as st

from settlement import (
    ELECTRONIC_RATES,
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


def dstr(value: Decimal) -> str:
    rounded = value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    return format(abs(rounded) if rounded == 0 else rounded, ",.2f")


def parse_uploaded_report(file_bytes: bytes) -> dict:
    """Session-only report cache: never share report bytes between logged-in accounts."""
    digest = hashlib.sha256(file_bytes).hexdigest()
    cached = st.session_state.get("parsed_upload")
    if cached is None or cached["digest"] != digest:
        cached = {"digest": digest, "report": parse_report(io.BytesIO(file_bytes))}
        st.session_state.parsed_upload = cached
    return cached["report"]


def read_parameters(rate_inputs: dict, ratio_input: str):
    rates = {game: Decimal(value.strip()) for game, value in rate_inputs.items()}
    ratio = Decimal(ratio_input.strip())
    if any(not v.is_finite() or v < 0 or v > 1 for v in [*rates.values(), ratio]):
        raise ValueError("倍率與結算比例必須是 0 到 1 之間的有限數字。")
    return rates, ratio


def upload_report():
    user_agent = st.context.headers.get("User-Agent", "")
    mobile_default = any(device in user_agent for device in ("iPhone", "iPad", "iPod"))
    if st.checkbox("手機相容上傳", value=mobile_default, key="compatible_upload"):
        from mobile_upload import compatible_file_uploader
        st.caption("iPhone 上傳失敗時可使用此模式，每份報表最多 10 MB。")
        return compatible_file_uploader()
    return st.file_uploader("報表上傳區（.xlsx）", type=["xlsx"])


def render_member_commission(uploaded, rates, ratio_input, *, agent_mode=False, environment="staging", download_scope=None):
    from member_commission import (parse_member_accounts, calculate_member_commission, export_member_commission,
                                   parse_agent_accounts, calculate_agent_commission, export_agent_commission)
    label = "代理" if agent_mode else "會員"
    sheet_name = "下線代理" if agent_mode else "直屬會員"
    cache_key = "agent_upload" if agent_mode else "member_upload"
    parser = parse_agent_accounts if agent_mode else parse_member_accounts
    calculate = calculate_agent_commission if agent_mode else calculate_member_commission
    exporter = export_agent_commission if agent_mode else export_member_commission
    try:
        data = uploaded.getvalue()
        digest = hashlib.sha256(data).hexdigest()
        cached = st.session_state.get(cache_key)
        if cached is None or cached["digest"] != digest:
            cached = {"digest": digest, "members": parser(io.BytesIO(data))}
            st.session_state[cache_key] = cached
        members = cached["members"]
        search = st.text_input(f"搜尋{label}帳號", placeholder="輸入完整帳號或部分文字", key=f"{cache_key}_search_{digest}").strip().casefold()
        matches = [key for key, member in members.items() if search in member["account"].casefold()]
        st.caption(f"「{sheet_name}」共 {len(members)} 個帳號，符合搜尋 {len(matches)} 個。")
        if not matches:
            st.warning(f"找不到符合的{label}帳號，請確認拼字或清空搜尋條件。")
            return
        if len(matches) > 50:
            st.info("先顯示前 50 個帳號，請輸入更多文字縮小搜尋範圍。")
        search_id = hashlib.sha256(search.encode()).hexdigest()[:16]
        chosen = st.radio(f"{label}帳號", options=matches[:50],
                          format_func=lambda key: members[key]["account"],
                          key=f"{cache_key}_account_{digest}_{search_id}")
        parsed_rates, ratio = read_parameters(rates, ratio_input)
        result = calculate(members, chosen, parsed_rates, ratio)
        st.subheader(f"{label} {result['account']} 的佣金明細")
        st.caption(f"來源：{sheet_name}。結算公式：（該帳號輸贏＋總佣金）×目前結算比例。")
        st.markdown(table_markdown([
            {"遊戲類型": game_label(game), "有效投注": dstr(item["valid_bet"]),
             "輸贏金額（參考）": dstr(item["win_loss"]), "倍率": str(item["rate"]),
             "佣金": str(item["commission"].quantize(Decimal('.01'), rounding=ROUND_HALF_UP))}
            for game,item in result["games"].items()
        ]))
        c1,c2,c3 = st.columns(3)
        c1.metric(f"{label}有效投注", dstr(result["total_valid_bet"]))
        c2.metric(f"{label}輸贏（參考）", dstr(result["total_win_loss"]))
        c3.metric(f"{label}總佣金", format(result["total_commission"].quantize(Decimal('.01'), rounding=ROUND_HALF_UP), ',.2f'))
        st.caption(f"未捨入佣金：{result['total_commission']}。過程保留精度，顯示採四捨五入至兩位。")
        c4,c5,c6 = st.columns(3)
        c4.metric("結算淨額", dstr(result["net_settlement"]))
        c5.metric("結算比例", str(result["settlement_ratio"]))
        c6.metric("最終結算", dstr(result["final_settlement"]))
        final = result["final_settlement"]
        if final < 0:
            st.error(f"{result['direction']}：{dstr(abs(final))}")
        elif final > 0:
            st.success(f"{result['direction']}：{dstr(final)}")
        else:
            st.info(result['direction'])
        st.caption(f"（{result['total_win_loss']} + {result['total_commission']}）× {result['settlement_ratio']} = {result['final_settlement']}")
        if "Sports" in result["games"] and result["games"]["Sports"]["rate"] == 0:
            st.warning("體育目前倍率為 0，佣金為 0；體育輸贏仍已計入結算。請確認左側倍率。")
        safe_account = re.sub(r'[^a-zA-Z0-9_.-]', '_', result['account'])[:64]
        st.download_button(f"下載{label}佣金 Excel", exporter(uploaded.name, result),
                           file_name=f"{ENVIRONMENTS[environment] if download_scope is None else download_scope}_{safe_account}_{label}佣金.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except (SettlementError, InvalidOperation, ValueError) as exc:
        st.error(str(exc))


def run_app(environment: str) -> None:
    st.set_page_config(page_title="Excel 代理結算系統", page_icon="🧾", layout="wide")
    st.title(f"🧾 Excel 代理結算系統｜{ENVIRONMENTS[environment]}")
    st.caption("版本：electronic-games-v1")
    if environment == "staging":
        st.warning("🧪 內部測試環境：請使用測試報表，結果不可作為正式付款依據。")
    account = require_login(environment)
    if st.secrets.get("access", {}).get("login_method") == "google":
        from google_access import render_management
        if render_management(environment):
            return
    mode = st.radio("計算模式", ["整體代理結算", "單一會員佣金", "單一下線代理佣金"], key="calculation_mode")
    member_mode = mode != "整體代理結算"
    agent_mode = mode == "單一下線代理佣金"
    data_dir = account_data_dir(BASE_DIR, environment, account)
    settings_file = data_dir / "settings.json"
    history_file = data_dir / "history.json"
    st.caption("上傳報表後，系統會從「下線代理」與「直屬會員」分頁加總，並以 Decimal 精準計算。")

    try:
        settings = load_settings(settings_file, group_electronic=True)
    except SettlementError as exc:
        st.error(str(exc))
        st.stop()
    with st.sidebar:
        st.header("佣金倍率設定")
        rate_inputs = {}
        if settings.get("migration_notice"):
            st.warning(settings["migration_notice"])
        for game in ELECTRONIC_RATES:
            rate_inputs[game] = st.text_input(
                f"{game_label(game)} 倍率", value=str(settings["rates"].get(game, ELECTRONIC_RATES[game])), key=f"rate_{game}"
            )
        ratio_input = str(settings.get("settlement_ratio", DEFAULT_SETTLEMENT_RATIO))
        st.header("結算比例設定")
        ratio_input = st.text_input("結算比例", value=ratio_input, key="ratio")
        st.caption("三種計算模式共用目前結算比例，預設 0.8。體育預設倍率為 0，可自行設定。")
        st.caption("電子類型＝Slots＋MiniGame＋Fishing，有效投注合併後乘以同一倍率；輸贏一併計入結算。舊設定先沿用 Slots 倍率。")
        if st.button("儲存設定", use_container_width=True):
            try:
                parsed, parsed_ratio = read_parameters(rate_inputs, ratio_input)
                save_settings(settings_file, parsed, parsed_ratio)
                st.success("設定已儲存，下次載入會沿用。")
            except (InvalidOperation, ValueError, OSError):
                st.error("設定必須是 0 到 1 的有效數字，且儲存目錄必須可寫入。")

    uploaded = upload_report()

    if member_mode:
        if uploaded:
            render_member_commission(uploaded, rate_inputs, ratio_input, agent_mode=agent_mode, environment=environment)
        else:
            st.info("請上傳報表，選擇下線代理帳號以計算單一代理佣金。" if agent_mode else "請上傳報表，選擇直屬會員帳號以計算單一會員佣金。")
        return

    if uploaded:
        try:
            report = parse_uploaded_report(uploaded.getvalue())
            rates, ratio = read_parameters(rate_inputs, ratio_input)
            result = calculate_settlement(report, rates, ratio)
            if "Sports" in result["games"] and result["games"]["Sports"]["rate"] == 0:
                st.warning("體育目前倍率為 0，佣金為 0；體育輸贏仍已計入結算。請確認左側倍率。")
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
            rows.append({"遊戲類型": game_label(game), "有效投注": dstr(item["valid_bet"]), "佣金倍率": str(item["rate"]), "佣金": dstr(item["commission"])})
        st.subheader("各遊戲有效投注及佣金明細")
        st.markdown(table_markdown(rows))

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
        st.download_button("⬇️ 一鍵下載 Excel 結算結果", output, file_name=f"{Path(uploaded.name).stem}_{ENVIRONMENTS[environment]}_結算結果.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        if st.button("儲存本次歷史報表紀錄", use_container_width=True):
            try:
                save_history(history_file, uploaded.name, result)
                st.success("歷史紀錄已儲存。")
            except (OSError, ValueError):
                st.error("歷史紀錄無法儲存，請聯絡管理者檢查資料目錄。")

    st.divider()
    st.subheader("我的歷史報表紀錄")
    st.caption("僅顯示目前帳號、目前環境的資料；Community Cloud 本機紀錄可能因重新部署或重啟而遺失。")
    history = []
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st.error("歷史紀錄讀取失敗，請聯絡管理者。")
            st.stop()
    if history:
        st.markdown(table_markdown(history))
    else:
        st.caption("尚無歷史紀錄。")
