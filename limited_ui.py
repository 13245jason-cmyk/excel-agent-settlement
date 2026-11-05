"""Public calculator restricted to one server-pinned original workbook."""
from decimal import InvalidOperation

import streamlit as st

from app_ui import dstr, parse_uploaded_report, read_parameters, render_member_commission, upload_report
from display_tables import table_markdown
from limited_report import LimitedReportError, checked_upload
from settlement import DEFAULT_RATES, DEFAULT_SETTLEMENT_RATIO, SettlementError, calculate_settlement, export_result_xlsx


def clear_report_state():
    for key in list(st.session_state):
        if key == "parsed_upload" or key.startswith(("member_upload", "agent_upload")):
            del st.session_state[key]


def run_limited_app():
    st.set_page_config(page_title="Excel 代理結算｜限制版", page_icon="🧾", layout="wide")
    st.title("🧾 Excel 代理結算系統｜限制版")
    st.caption("版本：limited-report-v1")
    st.info("免登入，僅接受指定的原始報表；修改或重新儲存的檔案會被拒絕。")
    st.caption("倍率與比例只保留在目前分頁，不保存報表、歷史紀錄或共用設定。")
    mode = st.radio("計算模式", ["整體代理結算", "單一會員佣金", "單一下線代理佣金"], key="limited_calculation_mode")
    with st.sidebar:
        st.header("佣金倍率設定")
        rates = {game: st.text_input(f"{game} 倍率", value=str(value), key=f"limited_rate_{game}")
                 for game, value in DEFAULT_RATES.items()}
        st.header("結算比例設定")
        ratio = st.text_input("結算比例", value=str(DEFAULT_SETTLEMENT_RATIO), key="limited_ratio")
        st.caption("三種模式共用目前倍率與結算比例。")
    uploaded = upload_report()
    if uploaded is None:
        clear_report_state()
        st.info("請上傳指定的原始 Excel 報表。")
        return
    try:
        verified = checked_upload(uploaded)
    except LimitedReportError as exc:
        clear_report_state()
        st.error(str(exc))
        return
    st.success("原始報表驗證通過。")
    if mode != "整體代理結算":
        render_member_commission(verified, rates, ratio, agent_mode=mode == "單一下線代理佣金", download_scope="限制版")
        return
    try:
        report = parse_uploaded_report(verified.getvalue())
        parsed_rates, parsed_ratio = read_parameters(rates, ratio)
        result = calculate_settlement(report, parsed_rates, parsed_ratio)
        st.subheader("各遊戲有效投注及佣金明細")
        st.markdown(table_markdown([
            {"遊戲類型": game, "有效投注": dstr(item["valid_bet"]), "佣金倍率": str(item["rate"]), "佣金": dstr(item["commission"])}
            for game, item in result["games"].items()
        ]))
        columns = st.columns(4)
        for column, label, key in zip(columns, ["總輸贏", "總佣金", "結算淨額", "最終結算"],
                                      ["total_win_loss", "total_commission", "net_settlement", "final_settlement"]):
            column.metric(label, dstr(result[key]))
        final = result["final_settlement"]
        if final < 0:
            st.error(f"代理需交上線：{dstr(abs(final))}")
        elif final > 0:
            st.success(f"上線需給代理：{dstr(final)}")
        else:
            st.info("雙方無需付款")
        st.caption(f"（{result['total_win_loss']} + {result['total_commission']}）× {result['settlement_ratio']} = {final}")
        if "Sports" in result["games"] and result["games"]["Sports"]["rate"] == 0:
            st.warning("Sports 目前倍率為 0，佣金為 0；Sports 輸贏仍已計入結算。")
        st.download_button("下載限制版結算 Excel", export_result_xlsx(report, result),
                           file_name="限制版_結算結果.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except (SettlementError, InvalidOperation, ValueError) as exc:
        st.error(str(exc))
