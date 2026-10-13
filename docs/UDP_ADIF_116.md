# ADIF UDP連携

「連携 → ADIF UDP連携設定」で有効化します。初期状態はOFFです。
同じPCなら送信先IPは127.0.0.1。初期例のポートは2236で、1～65535へ変更できます。
Log4OM2側でUDP Inboundのサービス種別を「ADIF MESSAGE」にし、受信ポートを同じ番号にしてください。WSJT-X向けの「JT MESSAGE」とは別です。
別PCの場合は相手PCのIPを指定し、そのPC側の受信設定を合わせます。IPv4/IPv6に対応します。

## 送信する内容

手動・通常の自動ログとも、PSRTTYのADIF保存が成功した新規QSOだけを送ります。
送信内容は既存のADIF出力と同じ1レコードのUTF-8テキストです。MODEはRTTY、日時はUTC、FREQはMHz。コール、RST、送受交換番号、自局コール、取得できた周波数/バンドを含み、EORで終わります。
WSJT-XのバイナリUDPプロトコルやN1MM XMLは送信しません。
既存QSOの編集・削除・過去ログ出力では送信しません。設定は無線機Profileに依存しない共通設定です。

## 送信状態

「UDP送信済み」はOSへの送信完了を示し、受信・ログ登録の確認ではありません。
受信側が停止中でも送信が成功することがあります。Log4OM2側のログで登録を確認してください。
送信失敗でもローカルのQSOは保持します。重複登録を避けるため、自動再送や起動後の再送キューはありません。
送信はバックグラウンドで行い、無線機の送受信処理と分けています。終了時は送信処理の完了を待ちます。
受信側の外部サービスへのアップロードは、Log4OM2側で設定してください。

## 根拠と確認範囲

Log4OM2公式の連携説明:
https://www.log4om.com/integrated/
公式Advanced Manual「Log4OM V2 connections explained」:
https://www.log4om.com/l4ong/usermanual/Log4OMNG_ENU_ADV.pdf
ADIF MESSAGEは、受信したADIF文字列を処理してログに登録する受信方式です。
実装はローカルUDP受信ソケットで確認しています。WindowsのLog4OM2本体との相互運用は未確認です。
