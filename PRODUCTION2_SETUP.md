# 正式版2（正式版1的相同功能副本）

正式版2從正式版1 `main` 的 `f3e2e31` 複製，使用獨立 `production2` 分支及同一個 `app.py` 入口。計算、登入、審核、倍率、歷史及下載的執行程式與正式版1完全相同，版本皆為 `electronic-games-v1`；本次不修改正式版1或測試站。

## 建立新 App

在 [Streamlit 預填部署頁](https://share.streamlit.io/deploy?repository=13245jason-cmyk%2Fexcel-agent-settlement&branch=production2&mainModule=app.py) 建立另一個 App：

| 欄位 | 值 |
|---|---|
| Repository | `13245jason-cmyk/excel-agent-settlement` |
| Branch | `production2` |
| Main file | `app.py` |
| App URL | 可自訂另一個名稱；以平台實際建立的網址為準 |

請建立新 App，不要改現有正式版1的網址、分支或主檔。若 Sharing 設為公開，訪客仍需通過 App 內的 Google 登入與授權；平台的訪客限制是另一層設定。

## 沿用正式版1的 Google 登入與核准帳號

使用者已選擇兩站共用正式版1已核准的帳號。到正式版1的 App settings → Secrets 複製設定，貼到正式版2的 Secrets；不要將密鑰貼到聊天或 GitHub。

沿用這些設定：

- `[deployment] environment = "production"`，不要改成 `production2`；分支名稱與授權環境是不同設定。
- `[access] login_method = "google"`。
- `[auth.google]` 原有的 Google Client ID、Client secret 及 discovery URL。
- `[authorization] admin_emails` 原有管理者。
- `[approval_db] url` **同一個正式授權資料庫**；若現有設定使用其他資料庫連線變數，也必須複製至新 App。新建另一個空資料庫不會沿用核准名單。

只調整新站自己的兩項 OAuth 設定：

1. `[auth] redirect_uri` 改為 **正式版2實際網址 + `/oauth2callback`**。
2. `[auth] cookie_secret` 換成新站專用的隨機值。可在自己的電腦執行 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 產生，直接填入新站 Secrets，不要提交 Git。

接著到 Google Auth Platform → Clients → 目前的網頁應用程式用戶端，在 Authorized redirect URIs **新增正式版2的相同回呼網址**；保留正式版1與測試站的原有回呼。儲存 Google 及 Streamlit 設定後，重新開啟正式版2。

公開範本為 `.streamlit/google-production2-secrets.example.toml`，內容都是占位值，不能直接登入。以原站的實際私有設定為準，避免覆蓋其他必要欄位或重複同名 TOML 區塊。

## 共用及獨立的範圍

- Google 核准、拒絕及停用使用同一資料庫的 `production` 權限。一站的管理者變更會影響另一站，既有正式核准帳號不用再申請。
- 兩站仍各自登入；不同網址的回呼與 cookie secret 不共用。管理者帳號沿用原設定。
- 報表與 session 快取只在各自 App 的工作階段；本機儲存的倍率與歷史不會自動由正式版1複製到正式版2。新站首次登入請確認倍率及比例。Community Cloud 本機檔案仍可能於重啟／重新部署遺失。
- 授權資料庫不保存 Excel 報表與結算金額。沒有將真實報表、帳密或 Secrets 複製進分支。
- `production2` 與 `main` 後續各自更新，不會自動同步。新功能仍依既定流程先測試，再由使用者決定要套用哪個正式站。

## 啟用驗收

本機驗證已確認 17 個執行／設定檔與正式版1 `f3e2e31` 完全一致（正式版1該版本已通過 147 項測試）。副本另通過 3 項針對性測試：正式／測試登入入口，以及兩個不同回呼與 cookie 設定的 App 共用核准和停權；這些測試使用合成 Google 身分與臨時授權資料庫，不代表真實 Google 登入已啟用。

正式版2須顯示 `electronic-games-v1`。以正式版1已核准的 Google 帳號登入，確認可直接使用；未核准帳號仍須申請。上傳自己的報表確認整體代理、單一會員、單一下線代理三種模式、電子類型合併、真人館與體育名稱、設定儲存及 Excel 下載。

程式副本與本機測試不代表新網址或真實 Google 回呼已啟用。公開網址必須由 Community Cloud 建立後確認；若出現 Google redirect 錯誤，先核對新 App 的 `redirect_uri` 與 Google 允許清單是否完全一致。
