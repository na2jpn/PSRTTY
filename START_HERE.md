# PSRTTY Ver1.16 正本フルソース — 2026-10-13

1.15最終正本を基に、1.16の機能とFIX1～FIX6をすべて反映しています。差分の追加適用は不要です。

Windowsでは build-windows.ps1 を実行してください。検証・EXEビルド後に release/PSRTTY_1.16.zip を生成します。
利用者設定・交信ログは同梱しません。更新時は既存のconfig・logdata・varを保持してください。

主な変更は周波数取得0.5秒、接続時の4モード選択、ADIF UDP連携、受信表示切替、FT-891対応、対応ICOM機種のUSB音声入力切替です。
受信表示の初期値は「まとめて」、接続時モードの初期値はLSB-D、ADIF UDP連携の初期状態はOFFです。

詳細は VERSION_116.md、docs/RELEASE_NOTES_116.md、docs/VALIDATION_116.md を参照してください。
以前のFIX資料とテスト結果は各段階の記録です。今後の開発はこの正本を基準にしてください。
