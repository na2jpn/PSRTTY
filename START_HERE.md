# PSRTTY Ver1.18 正本フルソース — 2026-10-15

1.18のFIX1～FIX7を統合した正本です。差分を追加適用する必要はありません。

- 標準はAFSK。FSKキーイングはProfileごとに切り替えられ、元のAFSK設定を保持します。
- FSK対応：ICOM 32項目、Kenwood 3機種、Yaesu 10項目。接続条件を機種別に案内します。
- USBケーブル接続で使用できる機種は黒、外部機器が必要な場合は青、直接FSK非対応の機種は赤で説明します。
- MACROボタン配色：表示メニューから、標準＋3つの名前付きプリセットを選べます。
- 設定・確認画面・初期設定ガイド・履歴は8言語対応です。

Windowsでは build-windows.ps1 を実行してください。テスト・EXEビルド後に release/PSRTTY_1.18.zip を生成します。
既存のconfig・logdata・varを保持してください。このソースZIPに利用者設定・交信ログは含めていません。

仕様は VERSION_118.md、Git用リリースノートは docs/RELEASE_NOTES_118.md、正本の検証記録は docs/VALIDATION_118_CANONICAL.md を参照してください。
FSK接続の資料は docs/FSK_ICOM_118_FIX3.md、docs/FSK_KENWOOD_118_FIX4.md、docs/FSK_YAESU_118_FIX5.md にあります。
ウェブ用ファイルは含めていません。過去版の資料・各FIXの検証記録は開発記録として保持しています。
