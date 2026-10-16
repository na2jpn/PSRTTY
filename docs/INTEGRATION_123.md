# Ver1.23 連携修正

## 公開版の扱い

Ver1.22は内部配布のみ・非公開。公開用のCHANGELOG、UPDATE_HISTORY、8言語の画面内履歴は、Ver1.21の次をVer1.23とし、Ver1.22のFSK対策もVer1.23に統合しています。過去の技術資料・検証記録は内部版の記録として残しています。

FSK用COMの接続中保持とPTT開始順序の修正は `docs/FSK_PORT_122.md` を引き継いでいます。FT-991AでVer1.22が動作したとのユーザー経由の報告があります。他機種での実機確認を意味しません。処理は機種共通で、対応する専用FSK用COMを使うYaesu・Kenwood・ICOMに適用されています。ICOMのCAT共用COMの所有権は維持します。

## HAMLOGのCALL・Enter・内容反映・保存

1. 入力ウィンドウを読み、空欄またはこのPSRTTYセッションで検索した未編集の入力欄であることを確認します。他の交信は上書きしません。
2. 再試行防止の転送記録をディスクに書き込みます。
3. CALLをコマンド `1 | THW_ENTER` で送り、HAMLOGのEnter相当の処理を行います。Enterキーの外部自動操作は使いません。
4. CALLを読み返し、対象のコールサインであることを確認します。違えば残りの入力と保存は行いません。
5. RTTYモードを先に設定してから、今回の交信の日付・時刻・送受信RST・周波数・備考を反映します。RST入力前にモードを設定し、モードによる桁数の影響を避けます。Enterにより設定された日時・RSTは今回のQSOの値に置き換えます。
6. CALL・日時・RST・周波数・モード・備考を読み返して照合します。
7. 自動保存を選んだ場合のみ、コマンド `18 | THW_SAVEBOX_OFF` を1回実行します。入力欄転送のみの場合は手動Saveです。
8. 保存指示後にCALL欄が空になったことを確認する既存処理は維持します。API応答はデータベースへの永続記録の受領証ではないため、表示は「保存指示」のままです。

HAMLOGのCode・GL・QSL・氏名・QTHは書き換えず、HAMLOGの既定値と検索結果を維持します。既存の照会済みCALLでも、交信転送時にEnter相当を行ってから最終内容を設定します。

## 照合エラー

- 不一致の各項目に、送信値と読戻し値を引用符付きで表示します。空欄は `""` と表示します。
- DATEは既存どおり2桁年／4桁年の同じ日付を許容し、FREQは有限の数値として比較するため末尾ゼロの違いを許容します。
- 各項目を独立して比較します。不正な日時や周波数が一つあっても、別項目まで誤って不一致として表示しません。
- RSTの59と599を同じ値と扱う変更はしていません。RST不一致ではHAMLOG側のRTTY・599形式の設定案内を追加します。
- 不一致・途中失敗・保存結果不明は従来どおり自動再送しません。PSRTTYのADIFは保存済みのため同じQSOを再登録しないでください。HAMLOG側で確認して未登録分だけ手動保存します。
- 設定画面、初期設定ガイド、同梱日本語・英語の連携説明に、RTTYを599形式（3桁）にする案内を追加しました。UI文言は8言語に対応します。

## Hamlibデバッグ出力

提供されたパッチを反映しています。

- `rig_set_debug` のctypes宣言：戻り値void、引数int。
- ライブラリ読込み後、`rig_init` より前に `rig_set_debug(0)` を実行します。
- Hamlib全モデルに共通で適用します。Hamlib内部のコンソール出力を抑制し、PSRTTYの戻り値確認・FSK診断・エラー表示は維持します。

## 根拠

- Turbo HAMLOG/Winの公開API `HamlogMs.txt`（Ver5.27c以降）： https://hamlog.xii.jp/mou/soft/Th527api.zip
- 同文書の公開PDF： https://mackey.my.coocan.jp/images/TurboHamlogMs.pdf
- CALLへコマンド1とTHW_ENTER、Saveへコマンド18とTHW_SAVEBOX_OFFというAPI仕様に基づきます。
- Hamlib公式API： https://hamlib.sourceforge.net/manuals/4.7/group__rig.html （RIG_DEBUG_NONE = 0）。

検証結果は `docs/VALIDATION_123.md` を参照してください。Windows版HAMLOGへの実接続とWindows EXEビルドはこの環境では実施していません。
