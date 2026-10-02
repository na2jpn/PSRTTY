# HAMLOG-CSV出力

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
