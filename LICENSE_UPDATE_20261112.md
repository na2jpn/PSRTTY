# PSRTTY 1.33 — 共通ライセンスへの切り替え

2026-11-12 / 対象: https://github.com/na2jpn/PSRTTY

基準コミット: `2f2db49b77d7aa47b84fdbc02ab6c2d8e204b1c6`

## GitHub Desktopで適用

1. PSRTTYを選んでFetch origin / Pull originし、既存の未コミット変更がある場合は同じファイルとの競合を確認してください。
2. Repository → Show in Explorerで、`psrtty.py`と`README.md`がある作業フォルダーを開きます。
3. 差分ZIP内のファイル・フォルダーを、その場所へ上書きコピーします。個人設定・ログ・実行時データ・Git管理情報は含みません。
4. Changesを確認してコミットします。例: `Adopt GPL-3.0-or-later and update eight-language license notices`。
5. Push originで反映します。公式サイトに残る旧配布条件も、新しい説明にそろえてください。

基準コミット以降に同じファイルを変更している場合は、上書き前に差分を照合してください。

## 変更内容

- リポジトリ直下に、改変していないGNU GPL v3本文の`LICENSE.md`と共通の`LICENSING.md`を追加。
- 作者表示を`Hiroshi Tanaka (JH1HST)`、PSRTTY本体のライセンスを`GPL-3.0-or-later`に統一。
- README、`docs/DISTRIBUTION_TERMS.txt`、8言語の「このソフトについて」から、無改変版の再配布禁止と必須の事前通知を整理。改良版の公開連絡は任意。
- 「このソフトについて」に、GPL全文と日英の共通説明をオフラインで開くボタンを追加。ボタン・文書読込エラーは全8言語で表示。
- 日本語エイリアスと内蔵英語フォールバックを更新。言語カタログは8言語・各1,449項目を検証。
- PyInstallerのEXE内にライセンス文書を収録。配布ZIPは`docs/LICENSE.md`、`docs/LICENSING.md`、`docs/DISTRIBUTION_TERMS.txt`をハッシュ計算前に現行ソースから同梱し、古いステージング文書を置き換えます。
- DISTRIBUTION_TERMS末尾のPycaw、comtypes、psutil等の第三者著作権・ライセンス本文は原文どおり保持。Hamlibその他の既存の表示・同梱ソース・データの個別ライセンスは変更しません。

バージョン番号は1.33を維持しています。このZIPはソース差分です。ビルド済みEXE・署名済みEXEは含みません。既存EXEの画面表示を変更するには再ビルドが必要です。

## 確認

- `python validate_languages.py --generate` と `python validate_languages.py` が成功。
- `QT_QPA_PLATFORM=offscreen python -m unittest -v tests.test_updater_101 tests.test_v102_fix4 tests.test_v111 tests.test_v112` — 21件成功。
- ステージング中の旧ライセンスが現行の本文で置き換わり、更新ZIPのハッシュ検証を通ることを確認。
- 設定・ADIF等を保持する既存更新テスト、旧版の互換ZIP、言語フォールバックの検証を実施。
- Qtオフスクリーンで8言語の作者・GPL表示と、合計16回のライセンス文書表示を確認。
- 共通2文書が原本と同一であること、第三者ライセンス本文を保持していること、Python構文と差分ZIPを照合。
- WindowsでのEXEビルド・実機操作・無線送受信・全テスト再実行・第三者資料すべての権利監査は実施していません。
