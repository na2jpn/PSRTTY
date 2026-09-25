# Ver0.77 ICOM追加機種

資料確認済み、実機未確認。既存機種の処理は維持。

|機種|既定CI-V|DATA ON + FIL1|資料の章／ページ|
|---|---|---|---|
|IC-7200|76|1A 04 01 01|CONTROL COMMAND pp.88–91|
|IC-7410|80|1A 06 01 01|CONTROL COMMAND pp.101–108|
|IC-7600|7A|1A 06 01 01（D1）|CONTROL COMMAND pp.159–167|
|IC-9100|7C|1A 06 01 01|CONTROL COMMAND pp.182–193|

共通：03 周波数読出、05 周波数設定、06 SSBモード設定、1C 00 00/01 RX/TX。
NB/NR/AN/MNは16 22/40/41/48。応答が不明・未対応なら操作を無効化。
機種の判別は選択したモデル名で行い、利用者がCI-Vアドレスを変更しても維持。
追加４機種は26 00によるフィルター操作を使用しない。本体側で切り替える。
ACKを確認できない送信要求は失敗扱いを維持。
USB音声デバイス選択・無線機のDATA変調入力USB設定は別途必要。
IC-7600はDATA1のUSB入力設定、IC-9100は運用するMAIN側の選択が必要。

確認元（公式資料、PDFの再配布はしない）：
- https://icomuk.co.uk/files/icom/PDF/productManual/IC-7200%20instruction%20manual.pdf
- https://icomuk.co.uk/files/icom/PDF/productManual/IC-7410_ENG.pdf
- https://www.icomjapan.com/support/manual/2615/
- https://icomuk.co.uk/files/icom/PDF/productManual/IC-9100_ENG_0.pdf
