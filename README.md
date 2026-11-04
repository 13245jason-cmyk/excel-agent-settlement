# Excel 代理結算系統（登入制）

Python + Streamlit + openpyxl + Decimal。支援 Google 登入後申請審核，以及管理者預先建立的帳密登入。正式使用與內部測試是兩個獨立 Streamlit Community Cloud App。

目前程式版本為 `google-access-v4`。Google 正式啟用請依 [GOOGLE_PRODUCTION_SETUP.md](GOOGLE_PRODUCTION_SETUP.md) 新增正式回呼及儲存正式 Secrets；設定尚未切換前沿用原有帳密。內部測試設定見 [GOOGLE_AUTH_SETUP.md](GOOGLE_AUTH_SETUP.md)。

## 兩個環境

| 用途 | Git 分支 | Main file | Secrets 的 environment | 網址 |
|---|---|---|---|---|
| 正式使用 | `main` | `app.py` | `production` | 現有 `https://excel-agent-settlement.streamlit.app/` |
| 內部測試 | `staging` | `staging_app.py` | `staging` | 在 Community Cloud 新增另一個 App，實際網址由平台設定／產生 |

兩站必須分別設定 Secrets。測試站有醒目的「內部測試」標示，下載檔名包含環境名稱。不要以網址參數切換環境；程式入口與 Secrets 的 environment 必須一致，否則鎖定功能。

## 帳密模式首次設定

更新後，尚未設定帳號的站台只會顯示「登入服務尚未設定完成」，不允許上傳、查看歷史或下載報表。沒有預設帳號或預設密碼，也沒有登入繞過模式。

### 1. 產生帳號設定

在你自己的電腦安裝 Python 3.10+，取得專案後執行：

```bash
python tools/create_user.py --username owner --environment production
```

程式會隱藏輸入並要求輸入兩次密碼（12–256 字元），只輸出含密碼雜湊的 TOML 設定，不輸出明文密碼、不寫檔。請勿把真實密碼貼到聊天、命令列參數或 GitHub。

Windows 可將 `python` 換成 `py`。此工具僅用 Python 標準函式庫，不需安裝 Streamlit。

### 2. 設定正式站 Secrets

在外部瀏覽器登入 [Streamlit Community Cloud](https://share.streamlit.io/)，找到現有 App，開啟 **App settings → Secrets**，貼入工具產生的設定並儲存。例如結構如下（占位文字不能直接登入）：

```toml
[deployment]
environment = "production"

[users.owner]
display_name = "管理者"
password_hash = "由工具產生的完整 pbkdf2_sha256 雜湊"
environments = ["production"]
```

範本位於 `.streamlit/secrets.example.toml`。若已有其他 Secrets，請保留無關設定、合併上述區塊。每個帳號名稱限小寫英數字、點、底線及連字號，最多 64 位。

### 3. 新增內部測試站

1. 在 Community Cloud 點 **Create app / Deploy an app**。
2. Repository 選 `13245jason-cmyk/excel-agent-settlement`。
3. Branch 選 `staging`，Main file 選 `staging_app.py`。
4. 設定獨立的測試站 Secrets：

   ```bash
   python tools/create_user.py --username tester --environment staging
   ```

5. 複製產生的設定至該 App 的 Secrets；其中 `deployment.environment`、帳號 `environments` 均為 `staging`。
6. 部署後複製平台提供的 `.streamlit.app` 網址，這才是實際測試站網址。若指定自訂名稱，需要確認名稱尚未被占用。
7. 使用合成測試報表驗證登入、修改倍率、儲存、歷史、下載及登出，再以正式帳號驗證正式站。

**兩站請使用不同密碼與各自的帳號設定。** 測試站的帳號不會自動取得正式站權限。正式站 Secrets 不應包含測試帳號。Community Cloud 後台的管理帳號，與網站內的結算帳號不同。

## 管理帳號

- 新增使用者：產生另一組設定，把新的 `[users.帳號]` 區塊加入該站 Secrets；`[deployment]` 只保留一份。
- 改顯示名稱：修改該帳號的 `display_name`。
- 重設密碼：重新執行工具產生雜湊，只替換該帳號的 `password_hash`。
- 停用使用者：從該站 Secrets 刪除對應 `[users.帳號]` 區塊。
- 沒有公開註冊或找回密碼頁面，密碼由管理者重設。

登入工作階段每次操作會重新驗證帳號與環境權限；修改密碼或移除帳號後，舊登入會失效。頁面存活時每 30 秒檢查一次工作階段，該檢查不延長閒置時間。閒置 30 分鐘或登入超過 8 小時須重新登入；登出會清除該工作階段的報表快取與倍率輸入。重新整理、斷線或開新瀏覽器分頁可能需要重登，不使用「永久記住登入」Cookie。

密碼以隨機 salt 的 PBKDF2-HMAC-SHA256（600000 次）保存，使用常數時間比較。相同站台程序中，同一帳號連續失敗 5 次會暫時阻擋，失敗紀錄保留 2 分鐘；其他瀏覽器工作階段也受限制。此限制是單一程序記憶體狀態，重啟會重設，不是跨伺服器的集中防護。

## 資料隔離與保存範圍

- 設定與歷史：`data/<production 或 staging>/<帳號 SHA256>/settings.json`、`history.json`。
- 每個帳號及環境各自保存；帳號不會看到別人的倍率或歷史。
- 報表解析快取只存在當前登入工作階段，不再使用跨使用者的全域 `st.cache_data`。
- 舊版 `data/settings.json`、`data/history.json` 不會刪除，但也不自動分配給任何新帳號。需要遷移時，先確認資料擁有者，再由管理者備份及遷移。
- 原始 Excel 不落地保存，但這是 **Streamlit 伺服器端解析**：上傳內容會傳送至 Streamlit 主機記憶體，不是瀏覽器端計算。
- Community Cloud 的本機檔案不保證跨重啟、重新部署永久保存，設定與歷史可能遺失；帳號設定在平台 Secrets 中獨立管理。若需要長期可靠的財務歷史，需要另接持久資料庫／儲存服務，目前未宣稱具備此能力。
- `data/` 與 `.streamlit/secrets.toml` 均由 Git 忽略。不要將真實財務報表、密碼、雜湊設定提交到公開儲存庫。

## 保留的結算規則

1. 從「下線代理」與「直屬會員」工作表，依「遊戲分類」「有效投注」「輸贏金額」欄位定位資料。
2. 只計算實際出現的已支援遊戲，缺少 MiniGame、Casino1、Casino2 不報錯、不補列。
3. LiveCasino1/2 映射為 Casino1/2。
4. 預設倍率：Slots `0.0258`、MiniGame `0.0258`、Casino1 `0.011`、Casino2 `0.007`、Sports `0`（自行設定）；結算比例 `0.8`。
5. 各遊戲佣金 = 有效投注 × 倍率；結算淨額 = 總輸贏 + 總佣金；最終結算 = 結算淨額 × 結算比例，使用 Decimal。
6. 負數「代理需交上線」、正數「上線需給代理」、零「雙方無需付款」。

登入制與隔離功能已建立；目前版本另擴充 `settlement.py` 支援 Sports、精確匯出與統一結算比例。先前檢查發現的空報表總計判斷、來源數值驗證問題仍需另行修正；既有測試通過不代表這些邊界問題已解決。

## 本機啟動

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell 改用：.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

把工具產生的設定儲存到本機 `.streamlit/secrets.toml`（不要提交 Git）。正式與測試入口要搭配正確 environment 的 Secrets：

```bash
streamlit run app.py
# 或：Secrets 改為 staging 後
streamlit run staging_app.py --server.port 8502
```

## 測試與發布

```bash
python -m pytest -q
python -m compileall -q authentication.py access.py app_ui.py app.py staging_app.py mobile_upload.py settlement.py member_commission.py approvals.py approval_ui.py google_access.py runtime_database.py display_tables.py tools
```

測試包括既有結算、密碼雜湊與驗證、缺少設定時鎖定、未登入不得存取報表、錯誤帳密與錯誤環境、嘗試次數限制、登入逾時／帳號停用／密碼更換、登出清除資料、每帳號與環境資料隔離、登入後只有 Slots 的報表仍能結算。測試使用合成資料與專用測試密碼。

未來開發先推送 `staging` 並驗證測試站，取得使用者對該次發布的明確同意後，只將已驗證的功能套用至 `main`。兩個分支的後續修改不會自動同步。只有平台完成部署並在實際網址測試後，才可確認線上版本已啟用。

## 本次驗證狀態

- 58 項 pytest 測試通過（包含既有 4 項結算測試）。
- 正式與測試入口的隔離副本均通過 Chromium 實際操作：未登入鎖定、兩站帳密互不通用、登入、僅 Slots 的報表上傳與結算、歷史保存、Excel 下載、登出後報表不可見。
- 瀏覽器操作只使用臨時合成帳號與合成報表，未建立任何正式使用者帳密。
- 實際 Community Cloud 上的帳號設定、第二個 App 建立，以及部署後正式／測試網址的登入驗證，仍需由擁有者完成平台設定後確認。

## 單一會員佣金與結算

此功能已開放於正式 `main/app.py` 與測試 `staging/staging_app.py`。登入後選「單一會員佣金」，上傳報表，在搜尋欄輸入完整帳號或部分文字，再從清單點選會員。搜尋不分大小寫；符合超過 50 個時先顯示前 50 個，搜尋仍涵蓋全部帳號。沒有符合帳號時會提示，且不顯示舊金額或下載按鈕。

- 只讀「直屬會員」分頁；依會員帳號、遊戲分類、有效投注、輸贏金額標題定位。
- 帳號不分大小寫；支援會員帳號欄合併儲存格。沒有明確帳號且不是合併儲存格的遊戲列會報錯，不猜測歸屬。
- 同一會員同一遊戲多列會加總；排除小計、合計、總計及其他會員。
- 顯示該會員實際出現的遊戲、有效投注、輸贏參考、倍率、佣金與總佣金；不補上未出現的遊戲列。
- 使用側欄目前倍率，修改後即時重算。會員佣金為各遊戲有效投注乘倍率的加總，同時依（該會員輸贏＋總佣金）×結算比例計算單一會員結算；此結果屬於所選帳號範圍。
- 可下載標示會員、來源與目前倍率的「會員佣金 Excel」。匯出保留 Decimal 精確字串，顯示四捨五入至兩位；帳號／檔名以純文字儲存，避免變成 Excel 公式。
- 會員清單及報表只快取在目前登入工作階段，登出清除；會員計算不混入整體代理歷史紀錄。
- 真實會員報表及其驗證數字僅在本機檢查，不提交儲存庫；回歸測試使用合成會員資料。

### 單一下線代理佣金與結算

在任一站台的「計算模式」選 **單一下線代理佣金**，上傳報表後，在「代理帳號」選擇要計算的代理。來源只使用「下線代理」工作表，依「代理帳號」「遊戲分類」「有效投注」「輸贏金額」定位，支援大小寫差異、欄位移動及帳號欄合併儲存格。

操作與單一會員相同：只顯示所選帳號實際出現的遊戲、排除小計及其他帳號，依目前倍率即時計算 Decimal 佣金，提供代理專屬 Excel 下載。佣金明細保留未乘比例的原始佣金，另依（該代理輸贏＋總佣金）×結算比例計算單一代理結算。代理與會員清單、快取及選擇欄位分開，切換模式不會混用兩個工作表的同名帳號。

此功能已開放於正式站與測試站，兩站各自使用自己的登入帳號、倍率與資料。測試不包含真實代理帳號或財務資料。


### Sports 與三種模式結算比例

- 支援報表中的 `Sports`（忽略大小寫），以有效投注乘左側 Sports 倍率計算佣金。預設倍率 0，首次使用由管理者自行設定；若維持 0 會明確提示，Sports 輸贏仍包含在結算內。
- 舊設定檔升級時只補上 Sports 倍率 0，其餘已儲存倍率與結算比例保持原值。
- 整體代理、單一會員、單一下線代理三種模式都顯示可修改的結算比例，預設 0.8，三種模式共用目前設定，按「儲存設定」後下次登入沿用。
- 三種模式統一公式：`結算淨額 = 所選範圍輸贏 + 總佣金`；`最終結算 = 結算淨額 × 結算比例`。先加佣金再乘比例，中間使用 Decimal 保留精度，顯示四捨五入至兩位。
- 單一帳號保留原始佣金合計，另顯示結算淨額、比例、最終結算、絕對應付金額及方向。下載 Excel 包含相同數據和比例，精確數值以文字保存，避免浮點與 Excel 數值精度限制。
- 報表未出現的遊戲不補列；所選帳號只包含自己的資料。正式站與測試站均提供此功能。


## 正式版發布：settlement-release-v1

本版將已驗證的測試版功能開放到正式 `main/app.py`：整體代理結算、單一會員、單一下線代理、Sports 倍率與三種模式的結算比例、Excel 匯出。正式站不顯示測試警語，單一帳號下載檔名標示「正式使用」；測試站保留「內部測試」標示。

登入設定、帳號權限與 `data/production/`、`data/staging/` 隔離方式不變，不會把測試站帳號或測試資料搬到正式站。正式站首次新增的 Sports 預設倍率為 0，請在左側確認正確倍率與比例後儲存。

Streamlit Community Cloud 需監看 `main`、Main file 為 `app.py`；平台完成自動更新後，登入可見版本 `settlement-release-v1`。若仍是舊版本，可在 Community Cloud 管理頁確認最新提交並重新啟動 App。正式站必須保留 `deployment.environment = "production"` 的 Secrets。

## 正式版發布：mobile-upload-v1

經使用者確認測試站可用並同意，將帳號搜尋與點選、一般結果表格、登入頁載入優化、手機相容上傳套用至正式 `main/app.py`。正式站為 https://excel-agent-settlement.streamlit.app/ ，登入頁版本顯示 `mobile-upload-v1`。Community Cloud 自動更新的完成狀態仍須在實際網址確認。

- iPhone、iPad、iPod 預設勾選「手機相容上傳」，其他瀏覽器亦可手動切換。相容模式僅接受非空白 `.xlsx`，每檔最多 10 MB；一般電腦上傳維持原有操作。
- 相容元件使用內嵌 JavaScript 與 FileReader，透過現有工作階段連線傳送檔案，避免選檔後再動態載入上傳用的 axios 模組。瀏覽器與後端均檢查大小、格式及編碼完整性，再交給既有 Excel 解析器；原始檔案不寫入磁碟，不放入跨使用者快取。每次登入建立獨立元件識別碼，登出清除。
- 整體、會員、代理及歷史明細改用一般表格，避免互動表格的額外載入依賴；小螢幕可橫向捲動，表格不再提供互動排序、選取或全螢幕工具，仍可下載 Excel。所有表格內容先跳脫 HTML。
- 登入前延後載入報表套件。開發環境五次全新 Python 程序量測的模組載入中位時間由 0.996 秒降至 0.397 秒；此數字不是遠端開站速度，無法消除主機休眠喚醒及網路延遲。
- 沿用正式站現有帳密登入、Secrets、佣金倍率、結算公式與環境資料隔離。本次發布不包含測試中的 Google 登入、授權管理或 Neon 整合，也不將測試帳號及資料帶到正式站。
- 測試站版本已通過 109 項自動測試與 Chromium 手機模擬的上傳、三種計算、下載、錯誤拒絕及登出流程，使用者亦已確認實際 iPhone Safari 可用。自動 WebKit 安裝受環境網路限制而未完成；不將 Chromium 模擬視為自動 Safari 驗證。
- 正式候選版通過 Python 編譯與 80 項測試，包含正式／測試環境的相容上傳與登出隔離。正式 `app.py` 隔離副本亦通過 Chromium 手機模擬：阻擋 axios 模組時仍可上傳、完成三種計算、下載標示「正式使用」的 Excel、移除及重選檔案、拒絕錯誤副檔名與登出。此 80 項為正式分支的測試集合，不含仍留在測試分支的 Google／Neon 測試。


## 正式版發布：google-access-v4

本版發布已在測試站驗證的 Google 原生 OIDC、使用申請、管理者核准／拒絕／停用與持久 PostgreSQL 審核，保留手機相容上傳及三種 Decimal 結算。同時將報表與歷史改為原生 Markdown 表格，避免顯示 HTML 原始碼。

- 管理者登入各站後可直接選「功能頁面 → 授權管理」，不需另外建立管理網站。各站只管理自己的環境，測試站核准的普通使用者仍須另申請正式權限；未核准或停用者不能上傳或下載報表。
- `approval_app.py` 保留為可選的獨立管理入口，與內建頁共用 `approval_ui.py`。所有申請與審核按 Google 穩定 subject 及環境隔離，確認欄綁定帳號、環境、revision 與決定，過期決定不能覆寫新結果。
- 依賴使用 `streamlit[auth]==1.66.1`，含 Google 轉址所需 HTTPX，修正缺套件造成的 Internal server error。CI 以獨立 venv 安裝，避免預裝套件掩蓋缺漏。
- 正式 Google Secrets 需由管理者在平台儲存，Cookie secret 與測試站不同，回呼為 `https://excel-agent-settlement.streamlit.app/oauth2callback`。正式站原本的帳密在切換 Secrets 前維持使用；Google 或資料庫設定錯誤時鎖定，不自動退回帳密。
- 原始報表不寫入授權資料庫。Google 使用者使用自己的資料空間，不自動搬移舊帳密的倍率或歷史；第一次登入應確認倍率與結算比例。
- 本次從隔離環境執行 Python 編譯與 126 項測試，包含兩個環境的 Google 申請、審核、撤權、不可跨環境核准、普通使用者無管理權、原生 OAuth 路由、手機相容上傳及既有結算。測試站管理者的真實 Google 登入已由使用者確認；正式站回呼與登入須在平台設定後實際確認。

正式站： https://excel-agent-settlement.streamlit.app/ 。完整設定及切換驗收見 [GOOGLE_PRODUCTION_SETUP.md](GOOGLE_PRODUCTION_SETUP.md)。未來改動仍先在測試分支驗證，取得使用者對當次發布同意後才更新正式分支。
