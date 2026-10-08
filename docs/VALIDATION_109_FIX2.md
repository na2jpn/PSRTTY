# PSRTTY 1.09 受信レベル案内の検証

2026-10-08（JST）。1.09の初回フルソースに対する累積差分で、独立ウィンドウの修正も含みます。

## 実装
- メインRXとAudio INの色を共通化。ゲージ目安は0～5%灰、6～39%水色、40～70%緑、71～89%黄、90～100%赤です。音声RMS由来の従来の目盛りを使い、無線機のS値や実際のクリッピング判定ではありません。
- RXゲージ近くに「受信レベル低：Audio INを確認」／「Low RX level: check Audio IN」を濃い水色で表示。長い説明はツールチップへ配置。
- 低レベル（0より大きく40%未満）に加え、直近2秒以内の空白以外の受信文字と新しい音声レベル通知があり、その状態が3秒続く場合だけ表示します。無信号だけでは表示しません。受信文字や音声通知が途切れた場合、レベル回復、送信中、デコードOFF、Audio IN切り替え時は解除します。無信号と弱信号の完全な識別や、受信不良の断定は行いません。
- RXの配色と案内は表示のみ。受信音量・デコーダー・スペクトラム表示感度を自動変更しません。クロススコープの描画処理も変更していません。
- ショートカットキーガイドを含む5画面の独立ウィンドウ構成を含み、メインを選んでもガイドは開いたままです。所有者なし・前面固定なし、メイン操作と呼び出し時のフォーカス移動を再確認しました。

## 検証
- 全520テスト: 失敗0、エラー0、環境制約によるローカルソケット1件スキップ（67.163秒）。
- 新規12テスト: 5色の境界、入力値の保護、無信号／デコードなしの抑止、3秒継続・回復・音声途切れ・送信／デコードOFF／入力切替、メインとAudio INの一致、音声設定不変、日英案内、ガイドを開いたままメイン操作と再呼び出し。
- 既存関連60テストも成功。Qtで日本語と英語の表示を描画し、案内の収まりとゲージ位置・文字色を目視確認。
- 新しい日本語trキーの英語辞書欠落なし。更新履歴は1.09の変更として日英で統合。版番号1.09、公開日2026-10-08を維持。
- Python構文、差分適用後の全ファイルSHA-256一致、ZIP CRCを確認。

Linux／Qt offscreenでの検証です。Windows実機の前後関係とタスクバー表示、Windows EXEビルド、実無線機・音声デバイスでの検証は未実施です。入力レベルが低いという表示だけで、音声配線の不具合やデコード品質を断定するものではありません。

## English
All 520 tests passed with one existing environment-related local-socket skip. Twelve new tests cover shared five-color boundaries, low-level notice gating/clearing, unchanged audio settings, translations and guide/main-window focus. Japanese/English layouts were rendered and visually checked. The notice requires recent decoded non-whitespace text and sustained low audio for three seconds; silence alone does not trigger it. Receive gain, decoding and cross-scope DSP are unchanged. This is a cumulative source patch containing the earlier independent-window correction. Real Windows stacking/taskbar behavior, EXE builds and radio/audio hardware remain untested.
