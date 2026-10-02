# PSRTTY Ver1.06 正本ソース

1.06の機能・修正を統合した全ソースです。このZIPだけで構成でき、過去の差分を適用する必要はありません。

Windowsでのビルド:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -v
./build-windows.ps1
```

出力は `release/PSRTTY_1.06.zip` です。この全ソースZIPをアプリ内の更新画面には指定しないでください。Windows EXEはこの環境ではビルドしていません。

既存の設定・Profile・マクロ・ログを維持する設計です。Languageの変更は再起動後に反映します。初期設定ガイド、更新履歴、マクロ編集、設定なども日英に対応しています。

変更内容は `UPDATE_HISTORY.txt` と `VERSION_106.md`、今回の確認は `VALIDATION_CANONICAL_106.md` を参照してください。開発途中の記録は検証資料として保持しています。
