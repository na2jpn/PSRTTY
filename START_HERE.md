# PSRTTY Ver1.09 全ソース

基準はPSRTTY_1.08_FULL_SOURCE.zip。1.09の変更を統合済みです。過去の差分ZIPの追加適用は不要です。
版表示1.09、更新履歴日付2026-10-08（日本時間）。

Windowsで build-windows.ps1 を実行してください。全テスト後、EXEとrelease/PSRTTY_1.09.zipを生成します。
このソースZIPはアプリ内ZIP更新用ではありません。

変更内容はUPDATE_HISTORY.txt、詳細はdocs/VER109_JA.md / VER109_EN.md、検証はVALIDATION_CANONICAL_109.mdを参照してください。
config・logdata・varには利用者の設定・交信履歴を同梱していません。既存の設定・プロファイル・ログを削除せず引き継いでください。
アイコンは正常なICOを継続使用しています。

独立ウィンドウへの修正を統合済みです。追加検証はdocs/VALIDATION_109_FIX1.mdを参照してください。
Window independence corrections are integrated; see docs/VALIDATION_109_FIX1.md.


RXゲージとAudio INの色・基準を統一しました。灰は表示なし、水色はLow、緑はGood（30～79%）、黄はHigh（80～89%）、赤はOver!（90%以上）を同系色でゲージ横に表示します。表示の細かな揺れと境界付近のちらつきを抑え、音声入力・デコード処理は変更しません。
Main RX and Audio IN share five level colors and matching labels: gray shows no text, light blue Low, green Good (30–79%), yellow High (80–89%) and red Over! (90% or more). Display smoothing and band confirmation reduce flicker without changing audio input or decoding.
検証: docs/VALIDATION_109_FIX3.md

2026-10-08: 1.09の修正を統合した正本です。差分の追加適用は不要です。RXゲージの説明は初期設定ガイド「波形の高さと入力音量」にも掲載。正本化検証: docs/VALIDATION_109_CANONICAL.md。
Canonical 1.09 source includes all corrections; do not apply earlier patches. See docs/VALIDATION_109_CANONICAL.md.
