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

世界のRTTY周波数ガイドを含めて1.12正本を更新（2026-10-09）。
- psrtty/frequency_guide.py: 共通の数値・出典・表生成（送信/無線機設定は変更しない）。
- psrtty/ui/frequency_guide.py: 独立したモデルレス5タブ。MainWindow.help_windowsで再利用。
- 表示文言freq.*は全8言語JSON、本体英語代替辞書にも反映。
- 全地域7 MHz欄に日本国内FT8 7.041 MHzの注意。USB/LSB、MARK/SPACEと全送信帯域を考慮。
- 1.8/1.9〜430 MHzを全地域、日本のみ1200 MHz。未確認のRTTY中心は推測しない。
- 第2地域の数値は米国ARRLの例と明示。第3地域2026年4月の提案は施行未確認につき採用しない。
- 出典と選定理由はdocs/RTTY_FREQUENCY_GUIDE_SOURCES.md。将来の変更時は公式資料を再確認する。
