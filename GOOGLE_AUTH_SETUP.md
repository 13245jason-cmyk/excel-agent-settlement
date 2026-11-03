# Google 登入與授權管理站（先測試，不更新正式站）

此功能只發布至 `staging`。`main` 與現有正式站帳密登入維持原樣。未來所有改動都先在測試站完成驗證，再由使用者明確同意後更新正式版。

## 使用流程

1. 在測試站點「使用 Google 登入」，由 Google 驗證身分。
2. 首次使用點「提出使用申請」；系統以 Google 穩定的 `sub` 身分識別碼建立待審申請，不允許輸入別人的信箱申請。
3. 待審、拒絕、停用者均無法上傳、查看或下載財務資料。
4. 管理者在另一個授權管理網站使用自己的 Google 帳號登入，選正式／測試環境，核准、拒絕或停用使用者。
5. 核准後，使用者點「重新檢查授權」即可使用該環境。正式與測試權限各自審核。
6. 撤銷後，下次操作或頁面每 30 秒的授權檢查會鎖定功能並清除報表狀態。資料庫離線時也鎖定，不能以 Google 已登入或舊帳密工作階段繞過。

只有 Secrets 中的 `authorization.admin_emails` 可以管理；第一位管理者直接由這份名單授權，不需要別人審核。Google 信箱需已驗證，並以 Google 原生登入驗證 ID token 的簽章、nonce、state、issuer、client audience。應用程式另檢查身分、信箱驗證與 token 到期，不接受自行提供的信箱或 query parameter 當作身分。

## 一、準備持久 PostgreSQL

可使用 Supabase、Neon 或其他受信任的雲端 PostgreSQL。管理站與測試站使用同一個**私有伺服器端資料庫**，程式透過 environment 欄位隔離權限。

- 從資料庫後台取得伺服器連線 URL（若含特殊符號密碼，須 URL encode）。不可填瀏覽器公開 anon key。
- 建議使用可由 Streamlit Community Cloud 存取的連線／pooler URL。
- 應用程式強制 `sslmode=verify-full` 並使用系統 CA 驗證伺服器憑證，不降級 TLS；本機 SQLite 只用於測試，不可作線上授權資料庫。
- 服務會在首次連線建立 `settlement_access_grants` 與 `settlement_access_audit`。資料庫帳號首次需有建立資料表的權限；也可由管理者先用 `tools/init_approval_db.py` 初始化，再使用已有表的讀寫角色。
- 只保存 Google subject、姓名、email、環境、審核狀態與審核操作紀錄，不保存 Excel 或財務明細。
- 申請唯一鍵避免重複申請；審核含 revision 檢查，過期頁面不能覆蓋另一個管理者剛完成的決定。申請及操作紀錄在同一交易中保存。
- 備份與存取權限由資料庫擁有者管理。停用網站或重新部署不會刪除外部資料庫紀錄。

## 二、建立獨立管理 App

在 Streamlit Community Cloud 新增 App：

| 欄位 | 內容 |
|---|---|
| Repository | `13245jason-cmyk/excel-agent-settlement` |
| Branch | `staging` |
| Main file | `approval_app.py` |

保留現有測試 App 的 `staging_app.py`。管理 App 需要另一個獨立網址；未設定完成時只顯示鎖定訊息，不開放審核。記下兩個實際 `.streamlit.app` 網址，不能把 GitHub 網址當作回呼網址。

## 三、Google OAuth 設定

在 [Google Cloud Console](https://console.cloud.google.com/) 選擇／建立你擁有的專案：

1. 在 Google Auth Platform 設定 Branding／Audience；只需要 `openid`、`email`、`profile`，不需要 Gmail、Drive 或其他財務存取範圍。
2. 建立 OAuth client，Application type 選 **Web application**。
3. Authorized redirect URIs 加入以下**實際網址**（每個網址必須精確相同）：

   ```text
   https://excel-agent-settlement-6p4duhxrtsjg78d7tuu2jo.streamlit.app/oauth2callback
   https://你的管理站.streamlit.app/oauth2callback
   ```

4. 若 Google 專案仍在 Testing 狀態，把管理者與參與驗證的 Google 帳號加入 Test users。將來對更多人開放前，依 Google 的要求調整 Publishing status；網站本身仍有申請審核，不會因此開放所有 Google 帳號。
5. 保存 Client ID、Client secret。**不要貼在聊天、README 或 GitHub**，只填到各站 Streamlit Secrets。管理者本人需在 Google Console 完成必要的登入及授權；本專案無法代造這些憑證。

原生 OIDC 參考：[Streamlit Google authentication](https://docs.streamlit.io/develop/concepts/connections/authentication)。

## 四、分別填兩站 Secrets

範本：`.streamlit/google-secrets.example.toml`。請替換全部占位文字，保留既有無關設定，不重複同名 TOML table。

| 設定 | 測試站 | 授權管理站 |
|---|---|---|
| deployment.environment | `staging` | `admin` |
| access.login_method | `google` | `google` |
| auth.redirect_uri | 測試網址 + `/oauth2callback` | 管理網址 + `/oauth2callback` |
| auth.cookie_secret | 獨立隨機字串至少 32 字元 | 另一組獨立隨機字串至少 32 字元 |
| auth.google.client_id / client_secret | 真正 Google Web client 設定 | 使用允許該 callback 的 Google Web client 設定 |
| authorization.admin_emails | 你的管理者 Google 信箱 | 相同管理者信箱 |
| approval_db.url | 私有 PostgreSQL URL | 同一個 PostgreSQL 資料庫 |

Cookie secret 可在你自己的電腦產生（輸出屬於機密，勿公開）：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

範本中的 `owner@example.com` 要換成你指定的 Google 管理者地址，**不是管理員可自行輸入別人的 email 登入**；仍必須由 Google 驗證該帳號。

設定 `access.login_method = "google"` 後，不再顯示帳密登入，也不會在 Google／資料庫設定失敗時回到帳密。若維持未設定或 `password`，則保留原有帳密功能供切換前繼續使用。Google 使用者的財務設定／歷史目錄依 `google:<subject>` 隔離，不自動取得舊密碼帳號的私人歷史。

Google OAuth 與持久資料庫尚未設定前，不要將測試站切換到 google。正式站本次完全不修改；測試成功並取得使用者同意後，才準備正式站 callback 與 Secrets 切換。

## 五、驗收清單

- 用非管理者 Google 帳號登入，未申請／待審時看不到報表控制項。
- 送出申請，在管理站以管理者 Google 帳號看到待審項目。
- 核准測試站權限，使用者重新檢查後可計算，正式站權限仍未核准。
- 管理者停用後，使用者下次操作／定期檢查被鎖定，報表狀態清除。
- 其他 Google 使用者開啟管理網址只看到拒絕訊息，不能查看申請名單。
- 重啟兩個 App 後，外部 PostgreSQL 中的審核狀態仍存在。
- Google token 過期後要求重新登入；使用者自行修改輸入／URL 不能冒用另一個 email。
- 審核資料庫中斷時不可進入報表，也不可顯示未確認寫入的審核已成功。

## 自動化與限制

```bash
python -m pytest -q
```

審核 service 可針對本機隔離 PostgreSQL 執行整合測試（僅允許 localhost 的 `approval_test` 資料庫）：

```bash
APPROVAL_TEST_DATABASE_URL='postgresql+psycopg://postgres:本機測試密碼@127.0.0.1:55432/approval_test' python -m pytest -q tests/test_approvals.py
```

Google 身分與介面測試使用合成、由測試注入的已驗證 claims，不是真正的 Google OAuth 成功登入。**真正的 Google redirect/callback、Google Cloud consent、雲端 DB TLS 連線與公開管理網址，必須在你填妥外部設定後實際驗證，不能以本機測試通過替代。**

本次已確認的測試網址：
https://excel-agent-settlement-6p4duhxrtsjg78d7tuu2jo.streamlit.app/

管理站的實際網址仍需先在 Community Cloud 建立 `approval_app.py` App 才能確認。不要把範例管理網址加入 OAuth 後當作已完成部署。

### 本次程式驗證

- 83 項自動化測試通過，涵蓋原結算功能、登入隔離及新 Google／審核流程。
- 19 項審核服務測試另外在隔離 PostgreSQL 17 執行並通過，包括並發申請、過期 revision、核准後重新連線持續有效與撤權。
- 介面測試以合成 Google claims 驗證「提出申請 → 管理者核准 → 開放報表 → 撤權後清除資料」；非管理者不能查看審核名單。
- 尚未取得 Google Web client 憑證、正式授權資料庫連線與管理站公開網址；真正 OAuth callback 及公開站台尚未驗證，現有登入方式保留。
