# 時刻基準（0.78）

|対象|基準|
|---|---|
|日時欄、自動時計、手動入力|JST固定 UTC+09:00|
|最新QSO、QSOログ一覧・編集、RX/TXカード|JST|
|生ログの日付・ファイル名|JST|
|ADIF QSO_DATE / TIME_ON|UTC|
|ADIF月別ファイル|交信日時のUTC年月|
|今月のADIFメニュー|クリック時のUTC年月|
|今日の生ログメニュー|クリック時のJST日付|

PCの時計は使用しますが、タイムゾーン設定には依存しません。
自動ログは送信完了時刻をUTCで記録、手動日時はJSTとして解釈します。
例：2026-10-01 00:30 JST → 2026-09-30 15:30 UTC → 202609.adi。
2026-10-01 09:00 JST → 2026-10-01 00:00 UTC → 202610.adi。
過去月の日時入力も交信日時を基準に振り分けます。
既存ファイル全体の移行は行いません。以前のファイル名・未知ADIFフィールドは維持。
QSOログ編集で月を変更すると対象レコードをUTC月別ファイルへ移し、未知フィールドも維持します。
移動前に両ファイルをバックアップし、保存エラー時は移動先を戻します。
二つのファイル更新はOS上で一括確定できないため、途中の電源断などではバックアップとの照合が必要です。
CabrilloのJST/UTC切替とUTC出力は従来どおりです。

YAESU表記確認元：
https://www.yaesu.com/jp/amateur_index/product/ft-991/index.html
https://connect.yaesu.com/indivisual/items/ftx-1series/
https://connect.yaesu.com/indivisual/wp-content/uploads/2025/11/FTX-1_CAT_OM_JPN_2512-D.pdf
表示名のみ変更し、既存の制御コマンドは変更しません。
