# データ形式・外部接続仕様

アプリ内ガイドはlanguage/*.jsonを正本とします。ADIF日時はUTC、ファイル振分けもUTC年月です。
表示のJST/UTC切替と保存基準を混同しないでください。既存ADIFの未知フィールドは保持します。

## HAMLOG CSV


ファイルメニューの罫線の下はADIF→Cabrillo→HAMLOG-CSVの順です。
期間・自局CALL→バンド→交信選択→確認・保存の順で出力します。

| 列 | 項目 | PSRTTYからの出力 |
|---|---|---|
|1|Call|相手CALL|
|2|Date|UTC記録からJSTへ変換、YY/MM/DD|
|3|Time|HH:MMJ|
|4|RSTs|相手に送ったRST|
|5|RSTr|相手から受けたRST|
|6|Freq|MHz|
|7|Mode|RTTY|
|8–12|Code / GL / QSL / Name / QTH|未記録のため空欄|
|13|Remarks1|SENT:送信番号 RCVD:受信番号（値があるもの）|
|14|Remarks2|MYCALL:運用自局CALL（チェックで出力可否を選択）|
|15|DX|未記録のため空欄|

CP932、BOMなし、ヘッダー・レコード番号なし、15項目、CRLF。各項目を二重引用符で囲み、内部の二重引用符を二重化します。交換番号からJCC/JCGを推測しません。Remarksが56バイトを超える場合、改行やCP932で扱えない文字がある場合は、文字を捨てず出力エラーとします。エラー時は既存の保存先ファイルも保持します。

参考：Turbo HAMLOG公式ヘルプ
- https://hamlog.sakura.ne.jp/html/HID00079.html
- https://hamlog.sakura.ne.jp/html/HID00020.html

## 登録クラブCSV


1.28以降は config/club_db.csv を編集・差し替えます。旧ルートのCSVとメタデータは、初回読込み時に内容を照合してconfigへ移動します。

UTF-8で保存してください（Excel等の「CSV UTF-8」も使用できます）。先頭行と例：

```csv
number,name
01A-1-1,ハムラジオ大雪クラブ
```

登録番号の先頭0、英字、ハイフンを消さないでください。編集後はCabrillo出力画面を開き直すと読み込みます。一覧にない場合はCLUB欄へ番号などを直接入力することもできます。

club_db_meta.json は確認日表示用です。CSVだけを編集した場合、古い確認日は表示されなくなります。CSVの使用にメタデータは必須ではありません。

同梱一覧：2026-10-19 JARL公開一覧照合、889件。
公開元：https://www.jarl.org/Japanese/A_Shiryo/A-B_Club/list.htm

独自に編集した一覧は別途保管してください。ソフト更新時には配布版の一覧で置き換わります。

## DXCC表示名


Entity identity and prefix matching remain based on psrtty/data/contest_prefixes.json and its existing licence. Localized territory names are generated from Unicode CLDR via Babel; runtime does not require Babel/pycountry. Subdivision names use explicit overrides where available. Rare island/entity proper names without a translation retain the database name; a parent country is never substituted for a distinct DXCC entity. This display data does not change contest scoring or the transmitted/received text. JD1 and /JD1 remain blank where the existing resolver cannot distinguish Ogasawara/Minami Torishima. No location is inferred from the user's own licence.

Unicode CLDR: https://cldr.unicode.org/ — Unicode licence: https://www.unicode.org/license.txt

## RTTYプリンター

基本プロトコル
・シリアル初期値115200 bps、8 data bits、no parity、1 stop bit。
・RTS/CTS、XON/XOFFなし。無線機／外部制御とは別のCOMを指定。
・USBオープン後1.5秒待ってから送出。リセット／起動が長い機器は対応調整が必要。
・7bit ASCIIテキスト、改行LF (0x0A)。初期32文字幅でアプリが折返し。
・1件は「MM-DD HH:MM:SS JST RX」等の見出し＋本文の複数行。
  時刻OFFでは見出しはRX/TXのみ。テスト印刷はTEST。
・日本語その他の非ASCIIや制御文字は?へ置換。CRとTABは空白へ置換。
  ESC/POSの制御コマンド、画像、カットコマンドは送らない。
・既定はACKなし、各物理行の送出後0.5秒待つ。0.05～5秒で調整可能。
  通常モードの送出完了は実際の印字完了を意味しない。

オプション：ACKモード（双方が対応している場合だけ有効）
・アプリはLFまで1行送った後、ASCII OK + LFを待つ（OK + CRLFも受理）。
・ブリッジはその行を確実に受け付け、次の行を処理できる時点で1回だけOKを返す。
  印字待ちが増え続けないよう、実印字完了または確実に空きがあるバッファと連動させる。
・OK受信後にも指定の行間隔を待つ。タイムアウト初期10秒（1～60秒）。
・行の送出前に受信バッファをクリアする。起動時の無条件OKや定期OKは送らない。
・OK以外の短い行は読み飛ばす。タイムアウト、接続エラーで印刷を停止。
・連番／重複検出／再送プロトコルはない。結果不明の途中ジョブは自動再送しない。
・このACK仕様はアプリ側の定義です。既存ファームが対応していると確認したものではありません。

過負荷・停止時の挙動
・印刷は独立ワーカースレッド。上限初期500件（10～2000件）。
・1件8192文字、待ち本文UTF-8合計2MiBも上限。上限に達すると新規受付を停止。
・満杯時は処理中の1件を完了し、それ以降の待ちを保持。接続エラー時は処理途中を再送しない。
・停止中に新規に到着した対象本文は印刷待ちへ追加されない。件数を状態のツールチップに表示。
・ステータス欄で通知。音、モーダルダイアログ、フォーカス移動はない。
・再開は原因を解消して出力をON。OFF／待ち消去／アプリ終了は未送出分を取り消す。
  PCやブリッジへ既に送ったデータは印刷される場合がある。待ちはディスクへ永続保存しない。
・起動時は必ず出力OFF。設定・RX/TX対象は保存される。

実機での確認手順
1. 無線機と別のCOM、速度、紙幅を選び、出力OFFのままテスト印刷を実施。
2. 見出しと本文、改行、文字欠け、文字化けを確認。必要に応じ行間隔を長くする。
3. メインRX、TX、RX+TX、1文字以下の除外、JST/UTCを確認。
4. 連続入力で欠落や装置バッファの溢れがないか確認。ACK対応ならACKを有効にして確認。
5. 切断・紙切れ・電源断・ACK停止の検出と再開、出力OFF、待ち消去を確認。
  ACKなしでは紙切れや装置内部の溢れをPCが検出できない場合がある。
6. 無線機操作やログ保存に遅延が出ないかWindows実機で確認。

English summary
USB serial, default 115200 8N1, no flow control. Printable ASCII + LF only,
32 columns, 0.5-second per-line delay, 1.5-second startup delay.
Optional per-line ACK is OK + LF (CRLF accepted); enable only with compatible
firmware. The bridge must reply when it can safely accept another line.
Default timeout: 10 seconds. No automatic retry of uncertain partial output.
The bounded worker queue pauses intake on overflow/error without UI dialogs.
Output defaults OFF at each launch. Physical printing and firmware compatibility
require hardware validation; this package contains the PC application only.

## Cabrillo

Cabrillo 3.0、ASCII、CRLF、日時UTC、モードRY。汎用・JARL WW RTTY・CQ WW RTTYの各プロファイルを用意します。大会カテゴリー・交換番号・提出先の条件を確認してください。

一次資料：
https://wwrof.org/cabrillo/
https://cqwwrtty.com/cabrillo.htm
https://www.jarl.org/Japanese/1_Tanoshimo/1-1_Contest/rtty_rule.html

## zLogサンプル

ZLOG_SAMPLE_*.adiはADIF出力例です。現在のリアルタイム連携はZ-Server経由です。両方で同一QSOを登録すると重複するため、用途を区別してください。
