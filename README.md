# PSRTTY 1.33 正本フルソース

公開日・正本化日：2026-11-04。1.32までの変更に加え、zLog MAX連携、8言語の設定先説明追記、FIX1を統合済みです。
今後の変更はこの正本を基準にします。以前の差分を追加適用する必要はありません。

WindowsではPowerShellで `./build-windows.ps1` を実行します。依存関係導入、ExtIOブリッジ再構築、
テスト、PyInstaller、完成EXEのIQ検査を経て `release/PSRTTY_1.33.zip` を作成します。

- [更新方法](docs/UPDATE.md)
- [開発・引き継ぎ](docs/DEVELOPMENT.md)
- [試験・確認範囲](docs/TESTING.md)
- [メーカー資料・FSK分類](docs/RADIOS.md)
- [データ形式](docs/FORMATS.md)
- [更新履歴](CHANGELOG.md)

機種別ガイド・ライセンスはdocs、言語ファイルはlanguage、外部依存はlibです。
アプリ配布ZIPのルートはpsrtty.exeとフォルダーのみ。Web用ファイルは別ZIPです。
新規の利用者向け表示・履歴は8言語対応です。

MAX内蔵サーバーの場合は「連携 → zLog MAX連携設定」から通常TCPで接続します。MAX側でZ-Linkサーバを起動し、端末承認を許可してください。接続先とポートはMAXの設定に合わせます。
外部Z-Serverを使う構成では、zLog MAX利用者も「連携 → zLog令和版連携設定」を使い、MAXと同じサーバー・ポートへ接続します。
