# PSRTTY 1.03 正本ソース

このZIP単独がVer1.03の開発基準です。1.02 FIX5、1.03差分、FIX1～FIX4までの修正をすべて含みます。以前の差分ZIPは重ねないでください。変更点は `VERSION_103.md`、検証結果は `VALIDATION_103.md`、次版への引き継ぎは `HANDOFF.md` を参照してください。

Windowsで `python -m pip install -r requirements.txt` → `python -m unittest discover -v` → `./build-windows.ps1` を実行します。PythonとPyInstallerが必要です。生成されるWindows配布ZIPは `release/PSRTTY_1.03.zip` です。この正本ソースZIP自体を運用中のPSRTTYフォルダーへ上書きしないでください。

Hamlib 4.7.2のDLL、対応ソースとライセンス通知は `lib/hamlib/` に同梱しています。配布条件の正本は `docs/DISTRIBUTION_TERMS.txt` です。1.01 EXEからの更新互換性のため、配布ZIPの直下には同一内容の `DISTRIBUTION_TERMS.txt` が一時的に置かれ、1.03の初回起動で整理されます。運用フォルダー直下はEXEとフォルダーだけになります。

## 更新方法

1.01以降からは、画面内の「PSRTTYのバージョンアップ」で**配布用** `PSRTTY_1.03.zip` を指定します。更新機能は `var/versionup.json` と配布manifestを照合します。`var/versionup.json` は配布ZIPを作る際に1.03用として生成されます。

0.88以前は画面内更新で追加ファイルを扱えません。PSRTTYを終了し、既存フォルダーをコピーしてから、**配布用**ZIPの中身を既存のPSRTTYフォルダーへ展開し、同名ファイルを上書きします。新しいフォルダーを既存フォルダーの中へ入れないでください。配布ZIPの `config/` と `logdata/` は空で、保存済み設定とログを維持します。

この正本ソースの `config/` と `var/` には旧版の実行時データを収録していません。
