"""Google administrator review controls, reusable in staging and its own app."""
from datetime import timezone
from zoneinfo import ZoneInfo

import streamlit as st

from approvals import ApprovalError
from authentication import ENVIRONMENTS
from display_tables import table_markdown

STATUS_LABELS = {"pending": "待核准", "approved": "已核准", "rejected": "未核准", "revoked": "已停用", "all": "全部"}
DECISION_LABELS = {"approved": "核准使用", "rejected": "拒絕申請", "revoked": "停用權限"}


def local_time(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")


def render_approval_management(store, identity, *, environments=("production", "staging")):
    # Check authorization before reading any applicant email or audit record.
    if not store.is_admin(identity):
        st.error("此頁面僅供授權管理者使用。")
        st.stop()
    if not environments or any(environment not in ENVIRONMENTS for environment in environments):
        raise ApprovalError("未知的授權管理環境")
    st.subheader("授權管理")
    st.caption("僅管理者可審核。以下時間為台北時間；不同環境的使用權限分開審核。")
    if len(environments) == 1:
        environment = environments[0]
        st.info(f"此頁只管理「{ENVIRONMENTS[environment]}」權限。")
    else:
        environment = st.radio("管理環境", environments, format_func=ENVIRONMENTS.get, key="approval_environment")
    if environment not in environments:
        st.error("無法管理此環境。")
        st.stop()
    status = st.radio("申請狀態", tuple(STATUS_LABELS), format_func=STATUS_LABELS.get, key=f"approval_status_{environment}")
    search = st.text_input("搜尋申請帳號", max_chars=256, key=f"approval_search_{environment}").strip().casefold()
    if st.button("重新整理申請"):
        st.rerun()
    if "approval_notice" in st.session_state:
        st.success(st.session_state.approval_notice)
        del st.session_state["approval_notice"]
    try:
        all_requests = store.list_requests(identity, environment)
        requests = [row for row in all_requests
                    if (status == "all" or row["status"] == status)
                    and (search in row["email"].casefold() or search in row["name"].casefold())]
        st.caption(f"符合條件：{len(requests)} 筆申請。")
        if not requests:
            st.info("目前沒有符合條件的申請。")
        else:
            if len(requests) > 50:
                st.info("先顯示前 50 筆，請用搜尋縮小範圍。")
            visible = requests[:50]
            st.markdown(table_markdown([
                {"Google 帳號": row["email"], "名稱": row["name"], "狀態": STATUS_LABELS[row["status"]],
                 "申請時間": local_time(row["requested_at"]), "更新時間": local_time(row["updated_at"])}
                for row in visible
            ]))
            by_subject = {row["subject"]: row for row in visible}
            chosen = st.radio("選擇申請", tuple(by_subject), format_func=lambda key: by_subject[key]["email"],
                              key=f"approval_request_{environment}")
            row = by_subject[chosen]
            decision = st.radio("審核決定", tuple(DECISION_LABELS), format_func=DECISION_LABELS.get,
                                key=f"approval_decision_{environment}_{chosen}_{row['revision']}")
            confirmed = st.checkbox(
                f"確認將 {row['email']} 的{ENVIRONMENTS[environment]}權限設為「{DECISION_LABELS[decision]}」",
                key=f"confirm_{environment}_{chosen}_{row['revision']}_{decision}")
            if st.button("套用審核決定", disabled=not confirmed) and confirmed:
                store.review(identity, chosen, environment, decision, row["revision"])
                st.session_state.approval_notice = "審核已儲存，使用者下次操作或定期檢查時生效。"
                st.rerun()
        with st.expander("最近 200 筆本環境授權操作紀錄"):
            emails = {row["subject"]: row["email"] for row in all_requests}
            records = store.audit_log(identity, environment=environment)
            if records:
                st.markdown(table_markdown([
                    {"操作時間": local_time(row["created_at"]), "Google 帳號": emails.get(row["subject"], "未找到對應帳號"),
                     "操作者": row["actor"], "動作": DECISION_LABELS.get(row["action"], "提出申請")}
                    for row in records
                ]))
            else:
                st.caption("尚無操作紀錄。")
    except ApprovalError as exc:
        st.error(str(exc))
    except Exception:
        st.error("授權資料庫暫時無法連線，未確認的變更不會顯示為成功。請重新整理後確認。")
