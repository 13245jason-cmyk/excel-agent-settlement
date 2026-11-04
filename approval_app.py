"""Separate Google-only authorization management website."""
import streamlit as st
from google_access import setup, google_identity
from approval_ui import render_approval_management

st.set_page_config(page_title='代理結算授權管理', page_icon='🔐', layout='wide')
st.title('🔐 代理結算授權管理')
_, store = setup('admin')
identity = google_identity()
if not store.is_admin(identity):
    st.error('此網站僅供授權管理者使用。')
    st.stop()

render_approval_management(store, identity)
