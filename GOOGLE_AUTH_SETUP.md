# Google 登入與申請審核（先內部測試）

程式只推送 `staging`。正式 `main` 與正式站的帳密登入維持現況；未來仍須使用者對每次發布明確同意後才更新正式站。

## 目前可用的程式流程

1. 使用 Google 原生 OIDC 登入，只要求 `openid email profile`。
2. 非管理者提出使用申請，待核准、拒絕、停用者均看不到報表操作。
3. 管理者登入同一測試站後，選「授權管理」，搜尋帳號並核准、拒絕或停用。**不必另外建立管理網站**，也不需要第三個 OAuth callback。
4. 此內建管理頁只管理內部測試，不能切到正式環境；申請與操作紀錄亦按環境隔離，時間顯示為台北時間。
5. 一般使用者重新檢查授權後可使用報表。停用後，下次操作或每 30 秒的定期檢查會鎖定功能並清除報表狀態。
6. 審核須勾選當前帳號、環境及決定的確認欄；更換決定會重新要求確認，過期 revision 不能覆蓋另一位管理者的決定。

只有 Secrets 的 `authorization.admin_emails` 名單可管理，且必須由 Google 驗證該信箱；不接受自行輸入 email 或 URL 參數作為身分。管理者由名單啟用，不需自己提出申請。所有其他 Google 使用者仍須審核。

## 現在尚缺什麼

目前開發環境沒有 Google Web client 憑證、Neon 連線網址，也沒有可操作 Google／Streamlit 管理後台的工具。程式與合成 claims 測試通過，不代表真實 OAuth 已開通。尚未填妥以下設定前，測試站保留原本帳密登入；不要提早切換 `access.login_method`。

只需三項外部值：

- Google Web application 的 **Client ID**。
- 同一用戶端的 **Client secret**。
- Neon 的私有 PostgreSQL **Connection string**。

不要把 Client secret 或資料庫密碼貼到聊天、GitHub、README 或命令列參數。請填入自己的本機私有設定檔，或直接填到測試站 Streamlit Secrets。

## 1. Google Cloud：建立網頁 OAuth 用戶端

1. 開啟 [Google Cloud Console](https://console.cloud.google.com/)，以管理者 Google 帳號登入，建立或選取一個專案。
2. 進入 **Google Auth Platform**，在 Branding 填應用程式名稱、支援信箱與聯絡信箱。名稱可用「代理結算測試系統」。
3. Audience 選適合自己的使用者類型；一般 Gmail 使用 **External**。先維持 Testing，將管理者與參加測試的 Google 帳號加入 Test users。
4. Clients → Create client，Application type 選 **Web application**。
5. 在 **Authorized redirect URIs** 加入以下完整網址，不能用 GitHub 網址或其他部署的網址代替：

   ```text
   https://excel-agent-settlement-6p4duhxrtsjg78d7tuu2jo.streamlit.app/oauth2callback
   ```

6. 儲存 Client ID 與 Client secret，填到測試站私有設定。原生 OIDC 不需要 Gmail、Drive 或其他資料範圍。

參考：[Streamlit Google authentication](https://docs.streamlit.io/develop/concepts/connections/authentication)。

## 2. Neon：取得原有專案的 PostgreSQL 網址

在 Neon Console 開啟原有 `casino` 專案（`muddy-smoke-07523588`），選先前指定的資料庫 branch `production`，按 **Connect**，複製提供給伺服器的 PostgreSQL Connection string。資料庫 branch 名稱不會把網站切到正式版。

只複製 `postgresql://` 開頭的完整網址，保留密碼及 SSL 參數；若畫面顯示 `psql 'postgresql://...'`，不要複製外面的 psql 指令與引號。建議使用 Neon 提供的 pooled runtime URL。

應用程式透過 SQLAlchemy + psycopg 強制 `verify-full`，驗證 TLS 憑證及主機名稱。首次連線建立 `settlement_access_grants` 與 `settlement_access_audit`，只保存身分與審核紀錄，不保存 Excel 或金額。SQLite 僅用於隔離測試，不可作線上授權資料庫。

## 3. Streamlit：只設定測試站

已替本次使用者在忽略版本控制的 `local-only/google-staging-setup/google-staging-secrets.toml` 準備私有設定檔：回呼網址與管理者已填、cookie secret 已隨機產生。該檔不是公開範例，不提交 Git；若工作區檔案不存在，使用 `.streamlit/google-secrets.example.toml` 自行建立。

1. 備份測試站現有 Secrets，方便需要時恢復帳密登入。
2. 在私有設定檔替換 `auth.google.client_id`、`auth.google.client_secret`、`approval_db.url` 三項占位文字。
3. 保留 `deployment.environment = "staging"`、`access.login_method = "google"`，確認 `authorization.admin_emails` 為自己的管理者 Google 信箱。
4. 到 [Streamlit Community Cloud](https://share.streamlit.io/) 找到下列測試站，開啟 App settings → Secrets，儲存完整設定；只變更測試站，保留任何其他必要服務設定，不重複同名 TOML 區塊。

   https://excel-agent-settlement-6p4duhxrtsjg78d7tuu2jo.streamlit.app/

5. 重新開啟測試站，用管理者 Google 帳號登入，應看到「功能頁面 → 授權管理」。內建管理頁只有內部測試權限；一般 Google 使用者只會看到申請或報表頁面。

切換為 Google 後不會在設定／資料庫失敗時退回帳密。Google 使用者資料按 `google:<subject>` 隔離，不自動取得舊密碼帳號的歷史或倍率。正式站 Secrets、帳號與資料此次均不變更。

## 實際驗收

- 用另一個 Google Test user 登入，先看到申請，無法上傳或讀取報表。
- 送出申請後，管理者在同一測試站核准；使用者重新檢查後可計算。
- 管理者停用使用者，使用者下次操作或定期檢查後被鎖定，報表狀態清除。
- 一般使用者無法看到管理頁；偽造頁面選擇也不會讀取申請名單。
- 重新部署測試站後，Neon 的審核紀錄仍存在。
- 資料庫離線、Google token 到期、設定錯誤時均鎖定，不得回到帳密繞過審核。

## 可選：獨立授權管理網站

`approval_app.py` 仍保留，與內建頁共用同一套審核控制項。在 Community Cloud 另部署 `staging/approval_app.py`，設定 `deployment.environment = "admin"`，自己的 callback、獨立 cookie secret、同一資料庫與管理者名單。此時才需要將它實際產生的網址加上 `/oauth2callback` 加入 Google 的 redirect URIs。

獨立入口可選正式／測試權限；這只管理授權紀錄，不能改變仍使用帳密的正式站登入方式。不要把範例網址當成已部署網址。本次不另外建立管理 App。

## 程式驗證與限制

```bash
npm run build
# 或
python -m pytest -q
```

本機 UI 以合成已驗證 claims 與隔離 SQLite 驗證授權，不是真實 Google OAuth。CI 的審核服務測試另外配置 PostgreSQL 17；也可對專用的本機 `approval_test` 資料庫設定 `APPROVAL_TEST_DATABASE_URL` 執行 `tests/test_approvals.py`。測試禁止指向非 localhost 或非 approval_test 資料庫。

本次 `google-access-v2` 通過 Python 編譯與 118 項測試；兩個隔離本機 Streamlit 程序另以 Chromium 驗證申請者送出申請、手機尺寸的管理者核准、申請者取得操作介面、管理者停用、下次操作鎖定。普通使用者看不到管理頁，過程無互動表格／Selectbox 模組請求或 JavaScript 錯誤。

真正的 Google consent／redirect／callback、Neon TLS 與公開測試站，仍須外部三項設定到位後實際驗證。此開發環境目前的外部網路權限也尚未放行 Google／Neon／Streamlit 站台，不宣稱已完成真實登入。
