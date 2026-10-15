# PSRTTY Ver1.20 — 2026-10-16

- FSKキーイング送信中も、取得可能なSWR・PWRを表示するよう修正しました。ICOM・Yaesu・Kenwood共通の修正です。
- FSK設定で無線機のRTTY／RTTY-Rモードを確認できた場合、ALCゲージの代わりに緑文字で「FSK」と表示します。
- FSK時は音量調整用のALC取得と「Audio設定チェック！」の案内を省きます。
- SWR・PWRの表示ON/OFF設定と、送信終了後2秒間の最終値保持は引き続き利用できます。
- 表示の説明と更新履歴を8言語で更新しました。

Ver1.19までの全機能・修正を含みます。

## 実装

標準はAFSK。FSKはProfile単位で選択し、従来の設定を保持します。
FSKではALCの値による音量評価を表示しません。
送信中のモード確認はFSK送信開始時の読返し成功を根拠にし、受信中はバックグラウンドでモードを読みます。
モード未取得・読取り失敗・取得から2秒経過の場合はFSKと断定せず「--」を表示します。
切断時は表示を隠します。
SWR・PWRは従来どおり有効な読取りを得た項目だけを表示します。
メーター読取りはGUIやFSKビット列の送信スレッドで実行せず、従来のBackgroundJobを使用します。
送信中はALCと追加のモード読取りを省いてSWR・PWRのみを取得します。
AFSKでは従来のALCゲージ・音量警告を維持します。

実装：psrtty/ui/main_window.py、psrtty/ui/tx_meters.py、psrtty/fsk.py、psrtty/audio_engine.py。
回帰テスト：tests/test_v120.py。検証記録：docs/VALIDATION_120.md。
