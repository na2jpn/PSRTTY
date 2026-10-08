# PSRTTY 1.10 差分（画面確認用）

適用基準: **PSRTTY_1.09_CANONICAL_FULL_SOURCE.zip**。初回1.09フルや修正途中のソースへ直接適用しないでください。
基準ZIP SHA-256: `de1f4f007608ab42b1c0b522dde34a92b9453b150984aa02b8a8073315151a1b`

1. PSRTTYを終了し、1.09正本フォルダーをコピーして作業用ソースを用意します。
2. 差分ZIPを別の場所へ展開します。
3. PSRTTY_1.10_PATCH内のpsrtty・tests・docs・ルートファイルを、作業用ソースの同じ場所へ上書きします。
4. Windowsでbuild-windows.ps1を実行します。出力はrelease/PSRTTY_1.10.zipです。

既存config・logdata・varは保持してください。ソース用差分で、アプリ内更新用ZIPではありません。公開日は未定。追加3言語の長文・一部操作表示は英語が残ります。docs/SCREEN_REVIEW_110.mdに画面確認項目、docs/VALIDATION_110.mdに検証と制限を記載しています。変更一覧はCHANGED_FILES_110.txtです。

## English
Apply only to PSRTTY_1.09_CANONICAL_FULL_SOURCE.zip. Exit, copy the canonical source as your working folder, extract this patch separately and overwrite matching source paths. Run build-windows.ps1; output is release/PSRTTY_1.10.zip. Preserve config, logdata and var. This is a source patch, not an in-app updater package. Publication date is unset. Russian/Chinese/Korean localization remains incomplete; some UI and long texts retain English reference text. See validation and screen-review documents.
