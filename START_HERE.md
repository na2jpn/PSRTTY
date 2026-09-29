# PSRTTY Ver1.05 正本ソース

このZIPだけでVer1.05の全ソースを構成します。「PSRTTYについて」の版表示を修正したVer1.05 VerFIX正本です。Ver1.04の確定版と、Ver1.05で動作確認されたProfile機能およびFIX1～FIX5の修正をすべて含みます。以前の差分を重ねる必要はありません。

Windowsでは `python -m pip install -r requirements.txt`、`python -m unittest discover -v`、`./build-windows.ps1` の順で実行します。生成される画面内更新用ZIPは `release/PSRTTY_1.05.zip` です。このソースZIPをアプリのバージョンアップ画面に指定しないでください。

既存の `config/psrtty.json`、`config/macros.json`、ログは保持します。旧版の設定はProfile1として読み込みます。詳しい変更点は `CHANGELOG.md`、アプリ内の説明は「ヘルプ → 初期設定ガイド」を参照してください。過去の試験用差分の説明書は `docs/history/1.05_trial/` に保存しています。
