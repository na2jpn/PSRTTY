# PSRTTY Ver1.15 正本フルソース（2026-10-12）

1.14正本を基に、1.15とFIX1～FIX4の変更を統合したフルソースです。差分適用は不要です。
Windowsでは `build-windows.ps1` を実行してください。8言語検査・全テスト・EXEビルド・配布ZIP検査を経て `release/PSRTTY_1.15.zip` を生成します。

既存の使用フォルダーへ更新する場合、config・logdata・varの利用者データを保持してください。このソースZIPには利用者設定・交信ログは含めていません。配布用EXE ZIPはビルド後に生成します。

新しいAudio IN／OUTは未選択です。対応する音声デバイスを選択してください。既存の自動設定と実ゲインは維持します。COMの自動選択は別設定です。
詳細: VERSION_115.md、docs/RELEASE_NOTES_115.md、docs/VALIDATION_115.md、docs/METERS_115.md。
過去版の資料は当時の履歴です。
