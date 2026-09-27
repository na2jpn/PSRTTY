# PSRTTY 1.03 正本からの引き継ぎ

次の開発は `PSRTTY_1.03_CANONICAL_SOURCE.zip` だけを基準にしてください。1.02正本、FIX5、1.03差分、FIX1～FIX4を再適用しないでください。

版は `psrtty/__init__.py` と `psrtty/config.py` が1.03です。表示、更新履歴、Windowsビルドも1.03に揃っています。変更の要約は `VERSION_103.md`、全体試験は `VALIDATION_103.md` を参照してください。

配布用ZIPはWindowsで `./build-windows.ps1` により作ります。ソースZIPと配布ZIPは別物です。Hamlib 4.7.2のDLL、対応ソース、ライセンス通知を `lib/hamlib/` に維持してください。1.01 EXEからの更新互換性として、配布ZIPには `DISTRIBUTION_TERMS.txt` の一時的な直下コピーが必要です。起動後は `docs/` の正本と照合して削除します。

`config/` と `logdata/` は利用者データです。更新処理が設定・ログを保持すること、`var/versionup.json` が新しい配布ZIPに含まれることを次版でも確認してください。画像送受信は後のバージョンへ延期しています。
