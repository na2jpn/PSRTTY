PSRTTY 1.07 / zLog 3.0.4.0 確認用サンプル（架空の交信）
These are SYNTHETIC QSOs. Import into a NEW disposable test log only.
実際の交信ではありません。必ず新規の試験用ログで読み込んでください。

GENERAL: SENT 001/002, RCVD 007/009. STX/SRX数値では1/2、7/9ですが、元のゼロ付き番号は文字列と備考に残ります。
JARL: SENT39、RCVD09。受信はAGEから9を取得、元の09は備考へ。
CQWW: W1ZZZ受信05 MA、DL1ZZZ受信14。CQZは5/14、STATEはMA。zLogの受信番号はCQZだけなので、W1ZZZは備考を見て州とマルチを修正してください。

全ファイルとも日時はUTC 2026-10-02 14:59と15:01。
JST表示なら2026-10-02 23:59、2026-10-03 00:01（日付またぎ）。
RSTは1件目S579/R589、2件目S589/R579。14.085 MHz/20mと7.04 MHz/40m、MODE RTTY。
自局CALLはJA1TEST。zLog側で自局CALLを設定してください。

Expected: 2 QSOs each; RTTY; 20m/40m; asymmetric sent/received RST.
Times: 2026-10-02 14:59 / 15:01 UTC, or 23:59 / next-day 00:01 JST.
zLog chooses exchange fields according to the selected contest. Check exchanges, leading-zero formatting, multipliers and own CALL after import.
CQ WW RTTY: zLog does not import STATE into the received exchange. Correct it using the original RCVD in COMMENT.
