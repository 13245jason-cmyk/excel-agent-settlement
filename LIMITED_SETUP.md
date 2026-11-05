# 免登入限制版

獨立入口為 `limited_app.py`，版本 `limited-report-v1`。此 App 不需要登入、Google OAuth、Neon 或 Secrets；原本 `app.py` 與 `staging_app.py` 的登入流程保持原功能。

## 接受的檔案

使用者指定的原始 `ExportStatisticalTotalExcel (5).xlsx`，長度 15,661 bytes。`limited_report.py` 固定原檔 SHA-256 及長度，每次上傳／重算都先檢查實際內容，再建立給解析器使用的已驗證快照，不以檔名或瀏覽器提供的大小當作驗證依據。

- 原檔改名但內容不變仍可用。
- 內容修改、重新儲存、重新匯出，或只改 Excel ZIP 中的附加資訊，都會拒絕，即使畫面上的數字相同。
- 同名其他檔案與網址參數不能覆蓋規則。拒絕或移除檔案後清除舊計算畫面及報表快取，沒有可用下載。
- 原始報表不包含在 Git、App 或安裝檔內，App 不提供原檔下載。使用者必須自行持有並上傳該原檔，未持有者看不到報表結果。

## 功能範圍

保留整體代理、單一會員、單一下線代理三種計算方式、可調佣金倍率與結算比例、Decimal 金額及 Excel 結果下載，支援原有手機相容上傳。下載檔名標示「限制版」。

匿名版的參數只保留於目前分頁工作階段，不寫入其他使用者可讀取的共用設定，不保存歷史紀錄，不使用或變更正式／測試站的帳號資料。報表仍傳至 Streamlit 伺服器記憶體進行檢查與計算，並非純瀏覽器處理。

## 本機啟動

```bash
python -m venv .venv
# 啟用 .venv 後
pip install -r requirements.txt
streamlit run limited_app.py
```

不需建立 `.streamlit/secrets.toml`。

## 部署獨立網站

在 Streamlit Community Cloud 建立新的 App，保留原有兩站的設定。可從 [預填部署頁](https://share.streamlit.io/deploy?repository=13245jason-cmyk%2Fexcel-agent-settlement&branch=limited&mainModule=limited_app.py) 開始；欄位如下：

| 欄位 | 值 |
|---|---|
| Repository | `13245jason-cmyk/excel-agent-settlement` |
| Branch | `limited` |
| Main file | `limited_app.py` |
| Secrets | 留空，不需填登入或資料庫設定 |

部署後設定新 App 的 Sharing 為公開（Public／Anyone with the link），讓訪客不需平台登入。公開網址由平台建立後確認，不將範例名稱當成已部署網址。此站已固定至獨立 `limited` 分支，不改正式 `main` 或既有 App 的 main file。

## 驗證

`npm run build` 通過 Python 編譯及 142 項測試。回歸資料為合成報表，未將原始財務報表加入 Git。涵蓋相同檔名／相同長度的不同內容、數字相同的重新儲存檔、只用驗證快照解析、拒絕前不解析報表、三種計算、下載標示、移除／替換後清除舊結果，以及匿名工作階段的參數隔離；原有登入與計算測試仍通過。

另外以指定原檔在隔離 Chromium 電腦與手機模擬中驗證原檔接受、改名接受、三種計算、下載、同名一位元組修改拒絕、網址 hash 覆蓋無效與舊畫面清除；未顯示私人帳號或金額於驗證輸出。手機為 Chromium 模擬，不代表本次已在實際 iPhone Safari 驗收。

## 將既有公開限制版切到獨立分支

若 Streamlit 部署設定允許編輯 Branch，將 `staging` 改為 `limited`，Main file 保持 `limited_app.py`，儲存並重新部署。若沒有可修改 Branch 的欄位，先用本頁預填連結另建 `limited` 分支的 App，驗收後再由使用者決定網址替換方式，不先刪除舊站。只有 Cloud 實際改用 `limited` 後，後續 `staging` 更新才不會自動部署到限制版。分支已建立不代表 Cloud 已切換。

目前使用者提供的獨立限制版網址：https://13245jason-cmyk-excel-agent-settlement-limited-app-limit-fsho8v.streamlit.app/ 。舊的 `limited-app-stagi-g7hcnd` 站未刪除，分享時請使用本段的新網址。
