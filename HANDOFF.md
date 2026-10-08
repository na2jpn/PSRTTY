# PSRTTY 1.09 引継ぎ

基準: PSRTTY_1.08_FULL_SOURCE.zip。全変更統合済み。build-windows.ps1でWindowsビルド。
詳細仕様: docs/VER109_JA.md / VER109_EN.md。版・日英更新履歴: 1.09 / 2026-10-08。
既存ログはADIFLogを継続使用。直入力の実際に音声へ渡した文字は送信終了時にraw transcript・TXカードへ記録し、プリンターは従来どおり正常送信完了した全文のみ既存のスプール経由で印刷。
Windows・実無線機・実音声デバイスによる確認は未実施。VALIDATION_CANONICAL_109.mdの検証範囲を参照。

5つの常用別ウィンドウはQWidget親なし。self.mainとMainWindowの参照で管理し、メイン終了時に明示して閉じます。クロススコープの位置保存もself.main経由です。


RXゲージとAudio INの色・基準を統一しました。灰は表示なし、水色はLow、緑はGood（30～79%）、黄はHigh（80～89%）、赤はOver!（90%以上）を同系色でゲージ横に表示します。表示の細かな揺れと境界付近のちらつきを抑え、音声入力・デコード処理は変更しません。
Main RX and Audio IN share five level colors and matching labels: gray shows no text, light blue Low, green Good (30–79%), yellow High (80–89%) and red Over! (90% or more). Display smoothing and band confirmation reduce flicker without changing audio input or decoding.
検証: docs/VALIDATION_109_FIX3.md

2026-10-08: 1.09の修正を統合した正本です。差分の追加適用は不要です。RXゲージの説明は初期設定ガイド「波形の高さと入力音量」にも掲載。正本化検証: docs/VALIDATION_109_CANONICAL.md。
Canonical 1.09 source includes all corrections; do not apply earlier patches. See docs/VALIDATION_109_CANONICAL.md.
