# PSRTTY 1.14 引継ぎ

2026-10-10。基礎は1.13正本。全変更を統合したフル実装ソース。
Windows: build-windows.ps1 → release/PSRTTY_1.14.zip。

仕様 docs/VER114_JA.md、公開ソースの確認 docs/ZSERVER_SOURCE_REVIEW_114.md、検証 docs/VALIDATION_114.md。
psrtty/live_tx.py: LTRS待機とFIGS復帰。psrtty/ui/direct_tx.py: 1～9秒STOP選択。
psrtty/zserver_link.py: 通常TCP、永続キュー、サーバ読み戻し、再接続。UIはintegration_dialog.py。
手動/TU73記録成功後に転送。既存ADIF・HAMLOG・プロファイル・送受信機能は継承。
8言語、埋込み英語、ガイド・履歴を同時更新。
未確認キューは使用者データとして保全。編集/削除/逆同期は行わない。
WindowsのzLog/Z-Server実アプリ確認は未実施。利用者による確認前のフル実装版。
