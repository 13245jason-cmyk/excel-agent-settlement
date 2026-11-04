# Excel 代理結算系統（登入制）

Python + Streamlit + openpyxl + Decimal。採管理者預先建立帳號、不開放註冊，正式使用與內部測試是兩個獨立 Streamlit Community Cloud App。

## 兩個環境

| 用途 | Git 分支 | Main file | Secrets 的 environment | 網址 |
|---|---|---|---|---|
| 正式使用 | `main` | `app.py` | `production` | 現有 `https://excel-agent-settlement.streamlit.app/` |
| 內部測試 | `staging` | `staging_app.py` | `staging` | 在 Community Cloud 新增另一個 App，實際網址由平台設定／產生 |

兩站必須分別設定 Secrets。測試站有醒目的「內部測試」標示，下載檔名包含環境名稱。不要以網址參數切換環境；程式入口與 Secrets 的 environment 必須一致，否則鎖定功能。

## 第一次啟用登入（必要）

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
python -m compileall -q authentication.py access.py app_ui.py app.py staging_app.py tools
```

測試包括既有結算、密碼雜湊與驗證、缺少設定時鎖定、未登入不得存取報表、錯誤帳密與錯誤環境、嘗試次數限制、登入逾時／帳號停用／密碼更換、登出清除資料、每帳號與環境資料隔離、登入後只有 Slots 的報表仍能結算。測試使用合成資料與專用測試密碼。

未來開發先推送 `staging` 並驗證測試站，再把同一版合併至 `main`，使正式站更新。兩個分支的後續修改不會自動同步。只有平台完成部署並在實際網址測試後，才可確認線上版本已啟用。

## 本次驗證狀態

- 58 項 pytest 測試通過（包含既有 4 項結算測試）。
- 正式與測試入口的隔離副本均通過 Chromium 實際操作：未登入鎖定、兩站帳密互不通用、登入、僅 Slots 的報表上傳與結算、歷史保存、Excel 下載、登出後報表不可見。
- 瀏覽器操作只使用臨時合成帳號與合成報表，未建立任何正式使用者帳密。
- 實際 Community Cloud 上的帳號設定、第二個 App 建立，以及部署後正式／測試網址的登入驗證，仍需由擁有者完成平台設定後確認。

## 單一會員佣金與結算

此功能已開放於正式 `main/app.py` 與測試 `staging/staging_app.py`。登入後選「單一會員佣金」，上傳報表，再選擇會員帳號。正式版 `mobile-upload-v1` 與測試分支 `google-access-v2` 均使用帳號搜尋欄與點選清單。

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

## 帳號選取修正：account-picker-v1（測試分支）

針對 `Failed to fetch dynamically imported module: .../Selectbox.DYo6P43Q.js`，會員與下線代理改為「搜尋帳號＋清單點選」，避免帳號選取依賴載入失敗的 Selectbox 元件。此修正尚未套用 `main`；測試完成後需取得使用者對本次發布的明確同意。

- 搜尋不分大小寫，可輸入完整帳號或部分文字；清空可恢復清單。符合超過 50 個時顯示前 50 個，搜尋仍涵蓋全部帳號。
- 沒有符合帳號時明確提示，並清除本次畫面的計算明細、金額與下載按鈕。
- 89 項自動測試通過。隔離 Chromium 使用合成帳號與報表，刻意阻擋 Selectbox JavaScript，完成登入、上傳、會員及代理切換、搜尋、無符合結果與倍率重算；帳號操作未請求 Selectbox，無 JavaScript 錯誤。
- 這是避開失敗元件的修正，並未證實 Community Cloud 靜態檔案失敗的上游原因；遠端部署完成狀態需在站台確認。報表、佣金公式與登入設定不變。

## 登入頁啟動優化：account-picker-v2（測試分支）

保留上一版帳號搜尋與清單，並把 pandas、openpyxl、單一帳號計算模組延後載入。未登入時先顯示登入畫面；登入後才載入表格套件，讀取或匯出 Excel 時才載入 Excel 套件。登入頁即顯示版本 `account-picker-v2`，方便核對部署版本。

- 同一開發環境以五次全新 Python 程序量測 `import app_ui`，中位時間由 0.996 秒降至 0.397 秒。這只代表程式載入時間，不代表遠端開站時間或網路等待改善比例。
- `npm run build` 通過，包含 Python 編譯與 91 項測試。新增正式／測試入口的全新程序測試，確認匿名使用者可看見登入欄位，尚未載入報表套件，也看不到財務操作；既有測試驗證登入、報表解析、三種模式、Decimal 計算與 Excel 匯出。
- 這次改動僅發布 `staging`；正式站需取得本次發布的明確同意後才更新。GitHub 推送成功不代表已確認 Community Cloud 部署完成，請以登入頁版本確認。
- Community Cloud 主機休眠喚醒、部署與瀏覽器靜態檔案載入仍可能等待。若需避免主機休眠造成的首開延遲，需另外評估常駐主機及費用；目前沒有搬遷主機或變更平台設定。

## 上傳後表格相容顯示：report-display-v1（測試分支）

整體代理、單一會員、單一下線代理的結果與歷史紀錄改用一般 HTML 表格，透過已載入的 Markdown 元件顯示，避免額外下載互動表格的 DataFrame 模組。小螢幕可左右捲動；表格不再提供互動排序、選取或全螢幕工具，Excel 下載與計算保持原功能。所有欄名、內容及表格標籤都先跳脫 HTML，報表檔名不會被當成程式或標籤執行。

- 原版在隔離 Chromium 刻意阻擋 `DataFrame.*.js` 後，可重現上傳後的動態模組載入錯誤。修正版在阻擋 DataFrame、Table、Selectbox 模組時，完成報表上傳、整體金額、歷史保存與顯示、會員與代理選取、倍率重算及 Excel 下載；沒有請求上述模組，也沒有 JavaScript 錯誤。使用的帳號及報表皆為合成測試資料。
- `npm run build` 通過：Python 編譯與 94 項測試，包含顯示金額、HTML 跳脫與空表格不補列的回歸檢查。
- 此改動是減少前端載入依賴的相容修正。使用者尚未提供這次錯誤的完整站台與失敗 JavaScript 網址，不能據此確認遠端上游原因，其他元件或網路失敗仍可能需要另外排查。
- 僅發布 `staging`，正式 `main` 尚未更新；部署完成後登入頁顯示 `report-display-v1`，實際 Community Cloud 更新狀態仍需確認。

## 手機相容上傳：mobile-upload-v1（測試分支）

針對手機選檔後，檔案卡片顯示 `TypeError: Importing a module script failed` 的情況，新增「手機相容上傳」。iPhone、iPad、iPod 的 User-Agent 預設勾選，其他瀏覽器可手動切換；此辨識只影響介面預設，不影響帳號權限。一般電腦上傳仍使用原生上傳元件。

- 相容元件位於 `components/mobile_upload/index.html`，透過 Streamlit 自訂元件 API v1 傳遞選取檔案。JavaScript 全部內嵌，選檔後使用 FileReader 與現有工作階段連線，不再動態下載 axios 上傳模組。檔案仍傳到伺服器解析，並非純瀏覽器結算。
- 相容模式每檔最多 10 MB、僅接受 `.xlsx`；瀏覽器與 Python 都檢查格式及大小。後端另檢查編碼完整性、實際位元組大小，並交給既有 Excel 解析器驗證內容。錯誤明確提示，不產生替代結算結果。可移除及重新選檔；顯示檔名使用純文字。
- 元件只在登入後建立，每次登入使用新的元件識別碼，登出清除元件及報表狀態。程式不將原始檔案存到磁碟，也不在跨使用者的全域快取保存上傳內容。
- `npm run build` 通過：Python 編譯與 109 項測試，涵蓋相容上傳解碼、錯誤拒絕、三種模式、下載及登入工作階段隔離。
- 已以 Chromium 的 iPhone 尺寸、觸控及 User-Agent 模擬，刻意阻擋 `axios.*.js`：原生上傳可重現檔案卡片的模組錯誤；相容上傳不再請求此模組。這不是實際 iOS Safari 驗證。WebKit 下載被環境網路以 403 阻擋，仍需實機確認，亦尚未確認遠端 Community Cloud 部署完成。
- 僅發布 `staging`，登入頁版本為 `mobile-upload-v1`；正式 `main` 尚未更新。原有登入與三種結算公式保持原功能。

## 表格顯示修正：mobile-upload-v2（測試分支）

修正正式站截圖中表格 HTML 原始碼被當成文字顯示的問題：整體代理、單一會員、單一下線代理與歷史紀錄改用原生 Markdown 表格，不再將 HTML 傳給 Markdown，也不開啟 `unsafe_allow_html`。沿用既有 Markdown 元件，沒有增加互動表格或 HTML 元件的動態載入依賴。

- 欄名與儲存格內容皆視為純文字。檔名中的 HTML、連結、圖片、數學或 Markdown 符號會編碼；分隔符與換行不會產生額外欄列。計算公式、Decimal 精度、登入、手機相容上傳及 Excel 匯出保持原功能。
- `npm run build` 通過 Python 編譯與 112 項測試。Chromium 電腦及手機尺寸的瀏覽器檢查確認三種模式與歷史呈現真正的表格欄列，顯示金額正確、可重算及下載。另用含 `|` 與 HTML 的合成檔名驗證歷史仍維持欄數，未產生圖片或腳本元素。手機為 Chromium 模擬，非實際 Safari 引擎。
- 本次僅推送 `staging`，版本為 `mobile-upload-v2`；正式 `main` 已於前次核准發布 `mobile-upload-v1`，尚未套用這次表格顯示修正。需要使用者同意本次發布後才能更新正式站，Community Cloud 的實際更新完成狀態仍須另行確認。

## Google 登入與申請審核：google-access-v2（測試分支）

Google 原生 OIDC 登入及 PostgreSQL 持久審核已整合測試站。管理者使用已驗證 Google 帳號登入後，可在同一站的「功能頁面 → 授權管理」核准、拒絕或停用申請，不需要另架第三個網站。內建管理頁只管理內部測試，普通使用者看不到管理頁，不能以頁面參數取得權限。獨立 `approval_app.py` 仍可選用，並共用新的 `approval_ui.py`。

申請及操作紀錄採原生 Markdown 表格、帳號搜尋與清單點選，避開互動表格／Selectbox 的額外載入。確認欄與帳號、環境、revision、審核決定綁定，更換決定須重新勾選；後端仍以 revision 防止過期頁面覆蓋他人決定。本環境操作紀錄先在資料庫按環境篩選；台北時間顯示。

本次 `npm run build` 通過 Python 編譯與 118 項測試；另以兩個隔離本機 Streamlit 程序與 Chromium 驗證申請、手機尺寸管理者核准、開放報表、撤權後移除操作介面。使用合成 claims 與 SQLite，**不代表真實 Google OAuth 或 Neon 已成功**。外部 OAuth client／Neon 連線仍待設定，未切換 Secrets 前測試站仍使用原有帳密；設定完成後 Google 或資料庫失敗時鎖定，不退回帳密。

私有 Secrets 範本與精確設定步驟見 [GOOGLE_AUTH_SETUP.md](GOOGLE_AUTH_SETUP.md)。只發布 `staging`，正式站目前的帳密及 `main` 保持原狀。之後每次需求均先測試站完成，取得使用者對該次發布的明確同意後才更新 `main`；此流程也記錄於 `AGENTS.md`。

## Neon CLI 與環境變數整合（測試分支）

Neon 初始化設定與 Python 的 `DATABASE_URL`／`DATABASE_URL_UNPOOLED` 支援已加入；保留 SQLAlchemy + psycopg。`npm run build` 會執行 Python 編譯與測試，`npm start` 啟動 Streamlit 測試入口。真正的 Neon 部署、認證與端到端檢查狀態詳見 [NEON_SETUP.md](NEON_SETUP.md)，不能以本機測試通過替代真實資料庫驗證。
