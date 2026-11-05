# 四站發布與快速回復

站台分支、入口及網址記錄於 `deployments.json`。每次更新依既定流程先在測試站驗證，再由使用者指定要升級的正式站。

| 站台代號 | 分支 | 目前可用的穩定版本標籤 |
|---|---|---|
| `production1` | `main` | `release/production1/electronic-games-v1` |
| `production2` | `production2` | `release/production2/electronic-games-v1` |
| `staging` | `staging` | `release/staging/electronic-games-v1` |
| `limited` | `limited` | `release/limited/limited-report-v1` |

版本標籤固定指向已驗證的提交，不移動舊標籤。升級前另為該站目前版本建立新標籤（或保留回復工具產生的 backup），新版本驗證通過再以新的版本名標記。不要以重設分支或強制推送回復。

## GitHub Actions 快速操作

GitHub → Actions → **快速回復版本** → Run workflow：

1. 選站台，例如 `production1`。
2. 版本輸入 `electronic-games-v1`，或該站完整的 `rollback-backup/...` 標籤。
3. 先選 `preview` 查看目前／目標提交及變更檔案；不發布任何回復。
4. 確認要回復時選 `apply`，在 `confirm_site` 再次輸入同一站台代號。這是儲存庫管理者明確指定要操作的站台與版本，普通網站使用者沒有此功能。

工具在隔離工作目錄檢查目標版本的編譯及完整測試，保留目前的回復工具與工作流程，再以**新的提交**恢復該版本的程式。同一個原子推送同時發布目前版本的備份標籤與回復提交；測試失敗、分支保護拒絕或遠端有新提交時不會強制覆蓋。可以選新產生的 backup 標籤撤回這次回復。

此 workflow 首次須經使用者核准發布至預設分支 `main`，GitHub 才會顯示可觸發的操作入口；目前先在 `staging` 準備及驗證，不代表 Actions 按鈕已在正式儲存庫啟用。分支保護若禁止 Actions 推送，操作會停止，應照該儲存庫的審核流程發布，不繞過保護。

## 本機 CLI（已可從測試分支使用）

須在已設定 GitHub 寫入權限的專案內操作，安裝 `requirements.txt` 後：

```bash
python tools/rollback.py list --site production1
python tools/rollback.py preview --site production1 --version electronic-games-v1
```

預覽會提供完整 `head`。確認站台及版本後，將該值填入：

```bash
python tools/rollback.py apply --site production1 --version electronic-games-v1 --confirm-site production1 --expected-head 預覽中的完整head
```

其他站替換 `--site`；限制版的版本為 `limited-report-v1`。全程不在目前工作目錄切分支，不覆寫未提交的工作，不將私有檔案、`.env`、Secrets 或報表加入發布。

## 回復的範圍

這是**程式版本回復**，不是資料還原：不更換 Google／資料庫密鑰，不還原授權資料庫、已儲存的倍率或財務歷史，也不更改 Cloud 的 App URL／部署分支。程式恢復與舊資料格式不相容時，仍需個別評估與資料遷移；不可承諾任意舊版本都能使用目前資料。

Streamlit 完成重新部署後，才會在網址顯示所選版本；部署可能造成短暫重新連線，Community Cloud 的本機資料仍可能遺失。此工具尚未提供資料庫備份還原。

## 公開限制版分離

`limited` 已從目前可用版本建立，後續不自動合併 `staging`。既有 Cloud 限制站必須改為從 `limited`／`limited_app.py` 部署，才能真正隔離。若平台不提供直接編輯 Branch 的欄位，先以 [獨立分支建立新 App](https://share.streamlit.io/deploy?repository=13245jason-cmyk%2Fexcel-agent-settlement&branch=limited&mainModule=limited_app.py)，驗收後再由使用者決定網址替換方式，不先刪除舊站。程式分支建立不代表 Cloud 設定已切換。

使用者已透過獨立分支部署流程提供新的公開限制版網址：https://13245jason-cmyk-excel-agent-settlement-limited-app-limit-fsho8v.streamlit.app/ 。四站清單與部署設定現以此網址為準，舊的 `limited-app-stagi-g7hcnd` 站未刪除。
