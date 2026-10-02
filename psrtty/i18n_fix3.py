"""FIX3 display translations."""
TEXT = {'時刻表記': 'Time display',
 'PCの時計を使用します。日時手動をONにすると更新を止めて編集できます。': 'Uses the PC clock. Enable Manual date / time to stop updates and '
                                         'edit.',
 '日時（{zone}）': 'Date / time ({zone})',
 '開始（{zone}）': 'Start ({zone})',
 '終了（{zone}、指定分を含む）': 'End ({zone}, inclusive minute)',
 '運用自局コール：{call}\n期間：{start} ～ {end} {zone}\nバンド：{bands}\nADIF出力：{count}件': 'Operating station: {call}\n'
                                                                            'Period: {start} – {end} {zone}\n'
                                                                            'Bands: {bands}\n'
                                                                            'ADIF export: {count} QSOs',
 '手動日時を正しく入力してから時刻表記を切り替えてください。': 'Enter a valid manual date / time before changing the time display.',
 '設定を保存できませんでした。': 'Could not save settings.',
 'RTTYプリンター': 'RTTY printer',
 'プリンター設定': 'Printer settings',
 'プリンター出力を有効にする': 'Enable printer output',
 '印刷する内容': 'Print content',
 '受信のみ（RX）': 'Receive only (RX)',
 '送信のみ（TX）': 'Transmit only (TX)',
 '受信と送信（RX＋TX）': 'Receive and transmit (RX+TX)',
 'プリンター設定…': 'Printer settings…',
 'テスト印刷': 'Test print',
 '印刷待ちを消去': 'Clear print queue',
 'プリンターのCOMポート': 'Printer COM port',
 '通信速度': 'Baud rate',
 '指定文字数以下は印刷しない': 'Do not print this many characters or fewer',
 '1行の文字数': 'Characters per line',
 '行ごとの送出間隔': 'Delay between lines',
 'ACKを待つ（対応ファーム用）': 'Wait for ACK (compatible firmware only)',
 'ACK待ち時間': 'ACK timeout',
 '印刷待ち上限（件）': 'Maximum queued jobs',
 '時刻を印刷する': 'Print timestamps',
 'プリンターのCOMポートを設定してください。': 'Set the printer COM port.',
 '無線機・外部制御と別のCOMポートを選択してください。': 'Select a COM port separate from the radio and external control.',
 'プリンター使用時は無線機のCOMポートを自動ではなく指定してください。': 'Specify the radio COM port instead of Auto when using the printer.',
 '出力をOFFにし、印刷停止を待ってから保存してください。': 'Turn output OFF and wait for printing to stop before saving.',
 '印刷待ちが空になってからテストしてください。': 'Wait for the print queue to empty before testing.',
 '待ち上限・受付停止': 'Queue full; intake stopped',
 '通信エラー・印刷停止': 'Connection error; printing stopped',
 '設定を確認': 'Check settings',
 '停止処理中': 'Stopping',
 'プリンター：{status}／待ち{count}件': 'Printer: {status} / {count} waiting',
 '出力OFF・待ち消去では送出済みの印刷は取り消せない場合があります。': 'Output OFF / Clear queue may not cancel data already sent to the '
                                       'printer.',
 '送出済み：{sent}件／受付漏れ・送出不明：{skipped}件': 'Sent: {sent} jobs / rejected or delivery unknown: {skipped}',
 'メインの受信・送信だけを印刷します。サブデコは含みません。短文判定は本文の前後の空白・改行を除いた文字数です。\nUSBシリアルへASCII＋改行で送ります。送出間隔は実機に合わせて調整してください。ACK使用時は各行へのOK応答が必要です。\n設定変更前に出力をOFFにしてください。OFFと印刷待ち消去は未送出分を取り消しますが、送出済みの印刷は止められない場合があります。': 'Prints '
                                                                                                                                                                                                  'main '
                                                                                                                                                                                                  'RX '
                                                                                                                                                                                                  '/ '
                                                                                                                                                                                                  'TX '
                                                                                                                                                                                                  'only, '
                                                                                                                                                                                                  'excluding '
                                                                                                                                                                                                  'sub '
                                                                                                                                                                                                  'decoders. '
                                                                                                                                                                                                  'The '
                                                                                                                                                                                                  'short-text '
                                                                                                                                                                                                  'filter '
                                                                                                                                                                                                  'counts '
                                                                                                                                                                                                  'body '
                                                                                                                                                                                                  'characters '
                                                                                                                                                                                                  'after '
                                                                                                                                                                                                  'trimming '
                                                                                                                                                                                                  'leading '
                                                                                                                                                                                                  '/ '
                                                                                                                                                                                                  'trailing '
                                                                                                                                                                                                  'whitespace.\n'
                                                                                                                                                                                                  'Sends '
                                                                                                                                                                                                  'ASCII '
                                                                                                                                                                                                  'lines '
                                                                                                                                                                                                  'over '
                                                                                                                                                                                                  'USB '
                                                                                                                                                                                                  'serial. '
                                                                                                                                                                                                  'Adjust '
                                                                                                                                                                                                  'the '
                                                                                                                                                                                                  'delay '
                                                                                                                                                                                                  'for '
                                                                                                                                                                                                  'your '
                                                                                                                                                                                                  'hardware. '
                                                                                                                                                                                                  'ACK '
                                                                                                                                                                                                  'mode '
                                                                                                                                                                                                  'requires '
                                                                                                                                                                                                  'an '
                                                                                                                                                                                                  'OK '
                                                                                                                                                                                                  'response '
                                                                                                                                                                                                  'to '
                                                                                                                                                                                                  'each '
                                                                                                                                                                                                  'line.\n'
                                                                                                                                                                                                  'Turn '
                                                                                                                                                                                                  'output '
                                                                                                                                                                                                  'OFF '
                                                                                                                                                                                                  'before '
                                                                                                                                                                                                  'changing '
                                                                                                                                                                                                  'settings. '
                                                                                                                                                                                                  'OFF '
                                                                                                                                                                                                  'and '
                                                                                                                                                                                                  'Clear '
                                                                                                                                                                                                  'queue '
                                                                                                                                                                                                  'cancel '
                                                                                                                                                                                                  'unsent '
                                                                                                                                                                                                  'data; '
                                                                                                                                                                                                  'data '
                                                                                                                                                                                                  'already '
                                                                                                                                                                                                  'sent '
                                                                                                                                                                                                  'may '
                                                                                                                                                                                                  'still '
                                                                                                                                                                                                  'print.'}
