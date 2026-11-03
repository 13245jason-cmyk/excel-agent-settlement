"""Separate Google-only authorization management website."""
import streamlit as st
from google_access import setup, google_identity
from approvals import ApprovalError

st.set_page_config(page_title='代理結算授權管理', page_icon='🔐', layout='wide')
st.title('🔐 代理結算授權管理')
_, store = setup('admin')
identity = google_identity()
if not store.is_admin(identity):
    st.error('此網站僅供授權管理者使用。')
    st.stop()

st.caption('只有 Google 已驗證身分且列於 Secrets 管理者名單的帳號可審核。')
environment = st.selectbox('管理環境', ['production','staging'], format_func=lambda e:'正式使用' if e=='production' else '內部測試')
status = st.selectbox('申請狀態', ['pending','approved','rejected','revoked','all'], format_func=lambda s:{'pending':'待核准','approved':'已核准','rejected':'未核准','revoked':'已停用','all':'全部'}[s])
if st.button('重新整理申請'):
    st.rerun()
try:
    requests = store.list_requests(identity, environment, None if status=='all' else status)
    if not requests:
        st.info('目前沒有符合條件的申請。')
    else:
        st.dataframe([{k:v for k,v in row.items() if k!='subject'} for row in requests], hide_index=True)
        index = st.selectbox('選擇申請', range(len(requests)), format_func=lambda i:f"{requests[i]['email']} · {requests[i]['name']}")
        row = requests[index]
        decision = st.radio('審核決定', ['approved','rejected','revoked'], format_func=lambda s:{'approved':'核准使用','rejected':'拒絕申請','revoked':'停用權限'}[s])
        confirmed = st.checkbox(f"確認對 {row['email']} 的本環境權限進行變更", key=f"confirm_{environment}_{row['subject']}_{row['revision']}")
        if st.button('套用審核決定', disabled=not confirmed):
            store.review(identity, row['subject'], environment, decision, row['revision'])
            st.success('審核已儲存，使用者下次操作或定期檢查時生效。')
            st.rerun()
    with st.expander('最近 200 筆授權操作紀錄'):
        st.dataframe(store.audit_log(identity), hide_index=True)
except ApprovalError as exc:
    st.error(str(exc))
except Exception:
    st.error('授權資料庫暫時無法連線，未確認的變更不會顯示為成功。請重新整理後確認。')
