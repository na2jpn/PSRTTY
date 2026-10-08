# PSRTTY 1.10 画面確認用 検証

開発確認日2026-10-08（JST）。公開日未定。基準はPSRTTY_1.09_CANONICAL_FULL_SOURCE.zipです。

## 実装・検証
- TX中は主ゲージをALCへ切り替え、RX通知による上書きを抑止。スペクトラム処理は変更していません。Audio INのRXゲージもALC値で動かさず、受信時の表示を保持します。送信終了時はRXに戻します。
- Audio OUTと主画面のGood判定／配色は共通のpsrtty/alc_display.pyを使用。ALC値1以下、動作開始音量の5ポイント下から開始点未満がGood（緑）。その他は調整中（ALC10以上は赤、それ未満は橙）。取得不可は灰色、数値なし、無線機確認／Check rig／各言語の短い案内です。
- Audio OUTで観測した動作開始点を既存audio設定へ追加保存。プロファイルごとに引き継ぎ、無線機モデル・COM・CI-Vアドレス／速度・PTT・停止ビット・接続時DATA設定・主出力先が一致する場合のみ参照します。実際の無線機の手動設定変更やUSB機器の物理的入れ替えまで検出するものではありません。
- 主ALCは送信中に最大毎秒2回、既存BackgroundJobで取得。別TX／切断世代の遅い結果は破棄。読み取り不可・エラーは取得不可表示です。Hamlibのread_alcは現在Noneを返すため、対応Yaesu／Kenwoodでは無線機確認となります。
- 5言語の選択／保存／再起動に対応。新規3言語は主要UIの明示的な短訳282項目と各言語の初期設定要点を収録。Qtの標準ダイアログ訳を同梱対象に追加。日本語／英語は従来の翻訳を継続します。
- **ロシア語／簡体字中国語／韓国語の完全翻訳は未完了です。** 長い案内、About、過去の履歴、未翻訳の操作項目には英語参照文が残ります。残存辞書キーはdocs/ENGLISH_REFERENCE_110.json（518項目）。完全翻訳済みの公開版として扱わず、ビルド画面確認用として使用してください。自動翻訳サービスはこの環境で利用できず、未確認の訳を埋めずに英語を維持しています。
- 全538テスト: 失敗0、エラー0、環境制約のローカルソケット1件スキップ（87.765秒）。追加11テストで判定・校正条件・保存・言語・TX切替・取得不可・設定との一致・過去TX結果破棄・Audio INの値を確認。
- Qt offscreenで日英露中韓の主画面・Audio OUT・ガイド・ダイレクト画面を描画。ALC取得不可案内の文字幅は確保。ロシア語の表示感度は短いМасштабへ調整。狭い主画面では既存のスクロールで操作領域を表示します。
- 版表記、ビルド出力1.10、JSONとQt翻訳ファイルの同梱設定、ICO維持、Python構文、ZIP CRC、正本への差分適用後SHA-256を確認。

WindowsでのEXEビルド、実無線機／音声デバイス、実際のALC取得と校正、Windowsフォントと前後関係は未確認です。1.09以前の検証資料は過去の記録です。

## English
This is an initial 1.10 screen-review patch, not a fully localized public release. RX switches to ALC during TX, with shared Audio OUT criteria, per-profile onset calibration, gray Check rig for unavailable values and stale-result rejection. Primary UI labels and quick guides support Russian, Simplified Chinese and Korean; unreviewed long texts and some controls retain English. The remaining catalogue keys are listed separately. All 538 tests passed with one existing environment skip. Windows builds and real radio/audio testing remain outstanding.
