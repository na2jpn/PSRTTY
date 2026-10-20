PSRTTY 1.27 正本ソース — 2026-10-20

1.27 FULLとFIX1〜FIX5を統合したフルソースです。過去の差分を追加する必要はありません。
このZIPを新しいフォルダーへ展開し、そのフォルダーでbuild-windows.ps1を実行してください。
Windows用の実行ファイル・配布ZIPは従来通りreleaseフォルダーに作成されます。
テスト：python -m unittest discover -s tests

既存運用のconfig / logdata / varはバックアップのうえ引き継いでください。
この正本ZIPに個人設定・交信ログは含めていません。
ネイティブIQドライバー／メーカーDLLは別途公式の案内に従って導入してください。

FIX5：表示メニューの「サブデコ」の直下にRYスキマー、RYレーダーを追加。
メイン画面のボタンと同じ独立ウィンドウを開き、開くたびに別窓を増やしません。
画面名は既存の8言語辞書を使用します。

docs/RELEASE_NOTES_127.md：統合した変更内容。
docs/RY_GUIDE_127_FIX4.md：RY画面・JA-BAND ONLY・IQ入力の案内。
docs/TEST_RESULTS_127_CANONICAL.txt：最終検証記録。
APPLY_127_FIX*.txtと各FIXの検証記録は過去の差分適用時の資料です。
正本へそれらの差分を再適用しないでください。
