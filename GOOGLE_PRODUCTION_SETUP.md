# 正式站 Google 登入啟用

正式入口為 `main/app.py`，網址 https://excel-agent-settlement.streamlit.app/ 。`google-access-v4` 包含 Google 登入、各站自己的申請審核、原生表格顯示、手機相容上傳與完整 OAuth 依賴。程式發布和登入切換是兩個步驟：正式 Secrets 尚未改為 Google 時，繼續沿用原有帳密。

## 1. 在原有 Google OAuth 用戶端新增正式回呼

到 Google Auth Platform → Clients → 先前建立的網頁用戶端，在 Authorized redirect URIs 新增：

```text
https://excel-agent-settlement.streamlit.app/oauth2callback
```

保留已使用的測試站回呼：

```text
https://excel-agent-settlement-6p4duhxrtsjg78d7tuu2jo.streamlit.app/oauth2callback
```

同一個 Web client 可同時允許這兩個 URI，不需要重新建立 Client ID。

## 2. 將正式專用設定儲存到正式 App

本次工作區已在 Git 忽略的 `local-only/google-production-setup/google-production-secrets.toml` 準備私有檔案，沿用已成功登入測試站的 Google 與 Neon 設定，並調整以下三項：

- `deployment.environment = "production"`
- `auth.redirect_uri` 為正式回呼網址
- `auth.cookie_secret` 為另一組獨立隨機值，不與測試站共用

其餘密鑰與管理者設定保留。此檔保持私有，不提交 Git 或貼到聊天。若私有檔案不在新工作區，公開範本為 `.streamlit/google-production-secrets.example.toml`，需要自行填入真正的 Google／資料庫設定及新的 cookie secret。

1. 確認 Google 已儲存正式回呼，且正式站程式已更新至 `google-access-v4`。
2. 在 Streamlit Community Cloud 找到正式網址的 App，確認 branch `main`、main file `app.py`。
3. 備份現有正式 Secrets。
4. 將填妥的整份正式專用 TOML 儲存到正式 App 的 Settings → Secrets，保留其他必要服務設定，不重複同名 TOML 區塊。
5. 從正式站首頁重新開啟，用指定管理者 Google 帳號登入；可在「功能頁面 → 授權管理」審核正式站申請。

兩站的環境、回呼與 cookie secret 不同，請使用對應檔案。Google 或授權資料庫出錯時會鎖定，不會自動退回帳密；需要恢復時由管理者在 Cloud Settings 還原備份的正式 Secrets。

## 3. 權限與資料驗收

- 內建管理頁各自固定在本環境：正式站只能審核正式權限，測試站只能審核測試權限。
- 測試站已核准的普通使用者，在正式站仍須另行提出申請；不複製測試授權、報表或歷史。
- Google 管理者由已驗證信箱與 Secrets 名單授權，不需自己提出申請。一般使用者看不到管理頁，未核准、拒絕或停用者不能操作報表。
- Google 使用者按穩定 subject 建立自己的資料空間，不自動搬移舊帳密帳號的倍率與歷史。第一次正式 Google 登入請確認佣金倍率與結算比例後再結算；需要搬資料時應先確認舊帳號歸屬，再另行備份與遷移。
- Neon 可共用同一個授權資料庫，grant、審核與 audit 均以環境隔離；其中不保存 Excel 或金額。
- Google 專案若仍處於 Testing，其他帳號可能受 Google 測試使用者名單限制。對外開放時須依 Google 要求調整 Audience 發布狀態；Google 專案公開不會跳過網站自己的申請審核。

正式環境的實際 Google redirect/callback 及登入切換，要在以上後台設定完成後於正式網址確認，不能僅以 Git 推送或本機合成 claims 測試當成已啟用。

## 本次程式驗證

`google-access-v4` 在隔離 Python 環境通過編譯與 126 項測試，包含正式／測試的申請、核准、撤權、管理頁權限隔離、手機相容上傳，以及原生 OAuth 路由的 HTTPX、state、nonce 與回呼拒絕檢查。使用者已回報測試站真實 Google 登入成功；正式回呼與正式登入仍待以上平台設定後確認。
