# ICOM FSK 機種別確認・実装（1.18 FIX3）

確認日：2026-10-15。選択肢52項目（複数型番をまとめた選択肢を含む）と「その他ICOM」を点検。

FSK対応32項目：USBキーイング8、外付けインターフェース経由のACC入力24。直接FSK非対応20項目はAFSKを案内。「その他ICOM」は仕様未確認として切替を許可しない。

機器の標準機能をメーカー作成の取扱説明書・CI-V資料で調べた分類。古い取説は保管サイト上のメーカー原本も参照する。改造・FSK信号を音声へ変換する外部装置は対象外。実機での全機種動作確認を意味しない。

| 選択項目 | 接続方式 | モード | メーカー作成資料（原本の保管サイトを含む） |
|---|---|---|---|
| IC-705 | USBキーイング | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.icomeurope.com/wp-content/uploads/2020/08/IC-705_ENG_CI-V_1_20200721.pdf) |
| IC-7300 | USBキーイング | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.icomjapan.com/support/manual/2574/) |
| IC-7300MK2 | USBキーイング | RTTY / RTTY-R | [取扱説明書・関連資料](https://icomuk.co.uk/files/icom/PDF/productManual/IC-7300MK2_ENG_Basic_0.pdf) |
| IC-905 | USBキーイング | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.icomeurope.com/wp-content/uploads/2024/07/IC-905_ENG_BM_1a.pdf) |
| IC-7100 | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.icomeurope.com/wp-content/uploads/2020/10/IC-7100_IM_GER_Full_20180131.pdf) |
| IC-9700 | USBキーイング | RTTY / RTTY-R | [取扱説明書・関連資料](https://icomuk.co.uk/files/icom/PDF/productManual/IC-9700_ENG_Basic_6.pdf) |
| IC-7610 | USBキーイング | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.f1nqp.fr/fichier/IC-7610/NOTICE_AVANCEE_ENG/IC-7610_ENG_Advanced_1.pdf) |
| IC-7760 | USBキーイング | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.icomeurope.com/wp-content/uploads/2025/01/IC-7760_ENG_CI-V_0.pdf) |
| IC-7851 | USBキーイング | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.radiomanual.info/schemi/ICOM_HF/IC-7850_IC-7851_user_2018.pdf) |
| IC-7200 | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://icomuk.co.uk/files/icom/PDF/productManual/IC-7200%20instruction%20manual.pdf) |
| IC-7410 | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://device.report/m/58864d170c195d3e44bae3768c88286c533b4f81177e155f0bfd4591091f58d2) |
| IC-7600 | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://rigreference.com/storage/manuals/icom/IC-7600%20manual.pdf--637af4b36385f7.45276476.pdf) |
| IC-9100 | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.radioamatore.info/attachments/499_IC-9100_user_manual.pdf) |
| IC-756PRO | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.manualslib.com/manual/281863/Icom-Ic-756pro.html) |
| IC-756PROII | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.qrzcq.com/pub/RADIO_MANUALS/ICOM/ICOM--IC-756ProII-user-manual.pdf) |
| IC-756PROIII | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.rigpix.com/icom/ic756proiii_manual.pdf) |
| IC-703 | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.qrzcq.com/pub/RADIO_MANUALS/ICOM/ICOM--IC-703-user-manual.pdf) |
| IC-7000 | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.radiomanual.info/schemi/ICOM_HF/IC-7000_M_S_user_JA.pdf) |
| IC-746 | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://manualzz.com/doc/37752949/icom-ic-746-instruction-manual) |
| IC-7400 / IC-746PRO | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://icomuk.co.uk/files/icom/PDF/productManual/7400um.pdf) |
| IC-7700 | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.manualslib.com/manual/605846/Icom-Ic-7700.html) |
| IC-7800 | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://icomuk.co.uk/files/icom/PDF/productManual/IC-7800_ENG_15.pdf) |
| IC-910 / IC-910H | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.rigpix.com/icom/ic910h_manual.pdf) |
| IC-706 | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.radiomanual.info/schemi/ICOM_HF/IC-706_S_user_JA.pdf) |
| IC-706MkII | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.manualslib.com/manual/4258799/Icom-Ic-706mkii.html) |
| IC-706MkIIG | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://manualzz.com/doc/8386225/icom-ic-706mkiig-instruction-manual) |
| IC-707 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.radiomanual.info/schemi/ICOM_HF/IC-707_user.pdf) |
| IC-78 | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.manualslib.com/manual/514302/Icom-Ic-78.html) |
| IC-718 | ACC 13ピン・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.qrzcq.com/pub/RADIO_MANUALS/ICOM/ICOM--IC-718-user-manual.pdf) |
| IC-725 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.manualslib.com/manual/4118092/Icom-Ic-725.html) |
| IC-726 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://manualzz.com/doc/62136831/icom-ic-726s-取扱説明書) |
| IC-728 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.icomjapan.com/support/manual/2755/) |
| IC-729 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.icomjapan.com/support/manual/2755/) |
| IC-735 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://rigreference.com/storage/manuals/icom/Manual-Icom_IC-735.pdf--5ea897fd5ef114.55342918.pdf) |
| IC-736 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.manualslib.com/manual/4593291/Icom-Ic-736.html?page=21) |
| IC-737 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.manualslib.com/manual/4147908/Icom-Ic-737.html) |
| IC-738 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.manualslib.com/manual/4593291/Icom-Ic-736.html?page=21) |
| IC-756 | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://www.radiomanual.info/schemi/ICOM_HF/IC-756_user.pdf) |
| IC-761 | ACC(1)・FSKインターフェース | RTTY | [取扱説明書・関連資料](https://www.qrzcq.com/pub/RADIO_MANUALS/ICOM/ICOM--IC-761-user-manual.pdf) |
| IC-765 | ACC(1)・FSKインターフェース | RTTY | [取扱説明書・関連資料](https://www.qrzcq.com/pub/RADIO_MANUALS/ICOM/ICOM--IC-765-user-manual.pdf) |
| IC-775 | ACC(1)・FSKインターフェース | RTTY / RTTY-R | [取扱説明書・関連資料](https://manualzz.com/doc/11249365/icom-ic-775-instruction-manual) |
| IC-781 | ACC(1)・FSKインターフェース | RTTY | [取扱説明書・関連資料](https://www.rigpix.com/icom/ic781_manual.pdf) |
| IC-271 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.radioamatore.info/attachments/833_IC-271_user_manual.pdf) |
| IC-275 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.icom.co.jp/support/manual/2666/) |
| IC-375 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.icom.co.jp/support/manual/2901/) |
| IC-471 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.icomjapan.com/support/manual/2791/) |
| IC-475 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.radioamatore.info/attachments/1358_IC-475_user_manual.pdf) |
| IC-575 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.icom.co.jp/support/manual/2504/) |
| IC-820H | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.manualslib.com/manual/3514580/Icom-Ic-820h.html?page=13) |
| IC-821H | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.radioamatore.info/attachments/1439_IC-821H_user_manual.pdf) |
| IC-970 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.icomjapan.com/support/manual/2889/) |
| IC-1275 | AFSK（直接FSKなし） | AFSK | [取扱説明書・関連資料](https://www.radiomanual.info/schemi/ICOM_VU/IC-1275_user_JA.pdf) |

## 接続上の区別

- IC-7300は単一USB COMのDTR/RTS。A/Bの表を出さない。
- IC-705・IC-7300MK2・IC-905・IC-9700・IC-7610・IC-7760はA/BのUSBキーイング信号を照合する。COM番号の大小から推測しない。IC-7610の実機表記はUSB1(A)/(B)。
- IC-7851はUSB1/USB2のDTR/RTSを選ぶ。A/B表と混同しない。
- IC-7100・IC-9100の2つのCOMを、USBキーイングが可能という根拠にはしない。本実装のFSK出力はACC用の独立したインターフェースへ接続。
- IC-7200・IC-7410・IC-7600も本実装ではACCからキーイング。USBはCAT/音声用に利用してもFSK入力とは別。
- 外付けインターフェースのFSK用COMはCATと分ける。同じ専用COMでFSKと外部PTTを行う場合、FSKとPTTはDTR/RTSの別々の信号線を使用し、一つのシリアルハンドルを共用する。
- 先行制御（prekey）用COMとFSK用COMは共用しない。
- RS-232の電圧をACCへ直接加えない。適合したインターフェースを使う。

## 資料の確認箇所

- USB機：USB SEND/Keying、USB Keying (RTTY)、USB/CI-V接続の節。IC-7300/IC-7851は Icom Tips for the USB port settings の第1節も参照。第3節の「2つのCOM」は第1節の対応機種一覧と別。
- ACC機：RTTY (FSK) connection、Operating RTTY (FSK)、ACC端子のRTTY入力。
- IC-761・IC-765・IC-781はRTTYのみを選択可能とし、RTTY-Rコマンドを送らない。シフト・Mark・極性は本体で設定。
- 旧型CI-V機のモード設定はフィルター番号なしの06コマンドとし、ACKと04応答のモードを確認してからPTTを許可する。
- 直接FSK非対応群：AFSK運用・音声MOD入力の接続説明、または標準モード仕様を参照。
- IC-375：メーカー日本語取説 p.22「データ通信について」でAFSK端末とLSBを指定。
- IC-575/IC-575D：メーカー日本語取説 p.34「データ通信の運用」でAFSKによるRTTYを指定。
- IC-970A/E/H：メーカー英語取説 p.12 Data communications のAFSK端末接続。
- IC-736/738・IC-737・IC-820H・IC-821H・IC-910H：取説のAFSK接続・運用説明でFSKモードを持たないことを確認。

## 実装の境界

AFSKの送信処理・既存Profileの選択方式は変更しない。FSK送信はAudio OUTを開かない。無線機側のUSBキーイング設定は自動変更しない。送信タイミング・極性・実際の端子は実機で確認が必要。非対応機種や未確認機種へ設定を書き換えた場合も、送信直前の検証で拒否する。
