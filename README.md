# PSRTTY 1.31 正本ソース

公開日：2026-10-24。1.30までの変更を統合済み。以前の差分は適用しないでください。

WindowsではPowerShellで `./build-windows.ps1` を実行します。依存関係導入、ExtIOブリッジ再構築、
テスト、PyInstaller、完成EXEのIQ検査を経て `release/PSRTTY_1.31.zip` を作成します。

- [更新方法](docs/UPDATE.md)
- [開発・引き継ぎ](docs/DEVELOPMENT.md)
- [試験・確認範囲](docs/TESTING.md)
- [メーカー資料・FSK分類](docs/RADIOS.md)
- [データ形式](docs/FORMATS.md)
- [更新履歴](CHANGELOG.md)

機種別ガイド・ライセンスはdocs、言語ファイルはlanguage、外部依存はlibです。
アプリ配布ZIPのルートはpsrtty.exeとフォルダーのみ。Web用ファイルは別ZIPです。
新規の利用者向け表示・履歴は8言語対応です。
