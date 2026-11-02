# Excel 代理結算系統

使用 Python、Streamlit、openpyxl 與 Decimal 製作的瀏覽器操作版代理結算系統。

## 功能

- 上傳 `.xlsx`，從「下線代理」與「直屬會員」工作表讀取資料並加總。
- 依欄位標題定位「遊戲分類」「有效投注」「輸贏金額」，不依賴固定儲存格。
- 支援 Slots、MiniGame、LiveCasino1/2（映射為 Casino1/2）。
- 佣金倍率與結算比例可在介面修改、儲存至 `data/settings.json`，下次載入沿用。
- 使用 `Decimal` 計算；缺少工作表、欄位、遊戲資料或不合法數值會明確報錯。
- 可下載結算結果 Excel，並將歷史紀錄保存至 `data/history.json`。

## 啟動

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

開啟 Streamlit 顯示的本機網址（通常是 `http://localhost:8501`）。

## 部署到 Streamlit Community Cloud

1. 將整個專案上傳到自己的 GitHub repository。
2. 登入 <https://share.streamlit.io>。
3. 選擇 **Deploy an app**，指定 repository、branch `main`、主程式 `app.py`。
4. 按 **Deploy**，完成後會得到可分享的 `https://xxxx.streamlit.app` 網址。

注意：目前設定與歷史紀錄保存於本機 `data/` 目錄。Community Cloud 重啟後，若要永久保存跨重啟資料，應再接 SQLite 雲端磁碟或外部資料庫；不建議把 `data/*.json` 提交到公開 repository。

## 測試

```powershell
pytest -q
```

## 計算規則

各遊戲佣金為有效投注乘以對應倍率；總佣金加上總計輸贏得到結算淨額，再乘以結算比例。最終結算小於零表示「代理需交上線」，大於零表示「上線需給代理」。

