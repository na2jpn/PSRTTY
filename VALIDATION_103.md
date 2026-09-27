# PSRTTY 1.03 正本検証 — 2026-09-28

- Linux上のQt offscreen環境で `python -m unittest discover -q` を実行：319件中318件成功、1件スキップ。
- `package_release.build_distribution` にダミーEXEを渡してZIP生成経路を確認。生成名 `PSRTTY_1.03.zip`、`inspect_zip(..., "1.02")` で版1.03として検証成功。これは配布形式の検査であり、Windows実行ファイルの動作確認ではありません。
- ソースの版表示、設定既定値、Windowsビルド手順、更新履歴を1.03へ統一。
- 旧版の `config/psrtty.json`、`config/macros.json`、`var/versionup.json` は正本ソースに含めず、配布ZIP作成時に1.03の更新データを生成する構成にしました。`config/` と `logdata/` は利用者データです。
- Hamlib 4.7.2のDLLと対応ソース・ライセンス通知を継承しています。

Windowsでの `build-windows.ps1` 実行と実機CAT操作の確認は、Windows・無線機のある環境で行ってください。
