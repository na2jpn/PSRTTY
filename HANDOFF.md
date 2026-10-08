# PSRTTY 1.11 正本 引継ぎ

本一式は1.09正本＋1.10画面確認差分＋1.11言語管理変更＋FIX1/FIX2を統合済みの正本です。
以前の差分を追加適用する必要はありません。
Windows: build-windows.ps1。出力: release/PSRTTY_1.11.zip。
仕様: docs/VER111_JA.md。検証: docs/VALIDATION_111.md。

表示文言はlanguage/*.json。共通キー・旧文言との対応はpsrtty/language_index.py。
本体の全英語代替辞書はpsrtty/english_fallback.pyで、en.jsonから
validate_languages.py --generate により生成します（Windowsビルドでも自動実行）。
キー変更は5言語を同時に更新してください。初期日本語、再起動反映を維持します。
英語代替表示で保存済みのui.languageを書き換えてはいけません。
送信マクロ・受信文・コール・機種識別・ログ/エクスポート内容は翻訳しません。
外部化後の日本語/英語文言を不用意に変更しないでください。
Windows実機ビルド・無線機/音声機器テストは利用者側で継続します。
