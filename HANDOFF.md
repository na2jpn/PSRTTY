# PSRTTY 1.12 引継ぎ

1.11正本（UTF-8テスト修正・履歴日付修正含む）を基準に8言語へ拡張。
更新履歴2026-10-09。Windows: build-windows.ps1 → release/PSRTTY_1.12.zip。
仕様 docs/VER112_JA.md、検証 docs/VALIDATION_112.md。

表示文言はlanguage/*.json。旧日本語との対応はpsrtty/language_index.py。
英語代替辞書psrtty/english_fallback.pyはvalidate_languages.py --generateで生成。
キー追加時は全8言語を更新し、辞書も再生成してください。
Qt標準ボタンはi18nのCatalogueTranslatorでカタログqt.*を利用。
インドネシア語・タイ語のqtbase qmがなくても保存/キャンセルなどを翻訳。
その他のQt標準文言はqmがあれば使用します。

初期日本語、再起動反映、英語代替、保存済みui.language保持を維持。
送信マクロ・受信文・コール・機種識別・ログ/エクスポートデータは翻訳しません。
追加言語は短く自然な操作名を選び、条件や差し込み項目を落とさないでください。
タイ語ガイドに対応フォント候補を指定。日本語/英語の既存文言を不用意に変更しないでください。
1.12更新ZIPは8言語必須、1.11の5言語検査との互換を維持。
Windowsのビルド・フォント・実機確認を継続してください。
