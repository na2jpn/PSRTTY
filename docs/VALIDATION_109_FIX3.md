# PSRTTY 1.09 RX表示の検証

2026-10-08（JST）。版番号1.09を維持。以前の独立ウィンドウ修正を含む累積差分です。

## 表示
- メインRXとAudio IN設定で、灰（0～5%）は文字なし、水色（6～29%）Low、緑（30～79%）Good、黄（80～89%）High、赤（90～100%）Over!。日英共通の短い表記をゲージ横に同系色で表示します。水色・黄色の文字は読みやすい濃さにしています。
- 従来の長い低レベル案内は短いステータスへ置き換えました。デコード文字の有無による表示条件はなく、音量の目安を常時表示します。グレーは空欄。ツールチップ・凡例・ガイドは日英対応です。
- 表示だけの平滑化: 上昇時定数120 ms、下降時定数450 ms。色／文字の境界変更は250 ms継続を確認してから行います。90%以上の入力は即座に赤／Over!を表示し、短い過大入力を隠しません。平滑化や境界確認の間は、瞬間入力値や表示値と色の切り替えに短い遅れがあります。定常入力では指定範囲に一致します。
- Audio INはメインと同じ平滑化済みゲージ値・色・文字を使用します。通知が750 ms以上途切れた場合、Audio IN切り替え、デコードOFF、送信開始時は表示状態をリセットします。
- 受信サンプル・音量設定・デコーダー・表示感度・クロススコープDSPは変更しません。数値は従来の音声レベル指標で、無線機のS値や実クリッピング検出ではありません。

## 検証
- 全527テスト: 失敗0、エラー0、既存の環境制約によるローカルソケット1件スキップ（67.252秒）。
- 追加7テスト: 定常境界値、上昇／下降の速度、ちらつき抑制と即時Over!、リセット、日英の両ゲージ一致、通知途切れ、メインのゲージ横配置。既存テストも仕様変更に合わせ更新しました。
- 日英のメインとAudio INをQtで描画し、Over!の収まりと配色、凡例を目視確認。
- 更新履歴は1.09の変更として統合。利用者向け履歴にFIX表記やサンクス変更を加えていません。
- Python構文と新規日英tr辞書、ZIP CRC、元1.09と各累積差分適用済み基準への上書き後SHA-256一致を確認。

Linux／Qt offscreenでの検証。Windows実機での表示応答・前後関係・タスクバー・EXEビルド、実無線機／音声デバイスは未確認です。従来の検証資料は過去の時点の記録として残します。現在のRX表示仕様はこの資料を参照してください。

## English
All 527 tests passed with one existing environment-related skip. Main RX and Audio IN share short colored labels and thresholds. Display-only smoothing uses a 120 ms rise / 450 ms fall, with 250 ms confirmation before ordinary band changes. Input at 90% or above immediately shows Over!. Stale input and receive-state changes reset the display. Audio gain and decoding remain unchanged. Japanese/English layouts were rendered and checked. Earlier validation files describe earlier source states; this document defines the current RX display. Real Windows and radio/audio hardware testing remains outstanding.
