# Kenwood FSK — 1.18 FIX4

2026-10-15。PSRTTYで選択できるKenwood 3機種をメーカー取扱説明書で調査し、FSK送信対象へ追加しました。実機送信確認済みという意味ではありません。

| 機種 | FSKキーイング入力 | 無線機のモード | メーカー資料・印刷ページ |
| --- | --- | --- | --- |
| TS-590SG | ACC2 2番 RTTY／4番 GND。外部FSKインターフェースが必要 | FSK / FSK-R | [取扱説明書](https://www.kenwood.com/usa/Support/pdf/B5A-0180-00.pdf) 39、72 |
| TS-890S | USB仮想COMのRTS/DTR。またはACC2 2番 RTTY／4番 GND | FSK / FSK-R | [取扱説明書](https://manual.kenwood.com/en_contents/attachDownload/109145) 1-4〜1-7、5-21〜5-22、16-12 |
| TS-990S | ACC2 2番 RTTY／4番 GND。外部FSKインターフェースが必要 | FSK / FSK-R | [取扱説明書](https://www.kenwood.com/usa/Support/pdf/TS-990S.pdf) 1-5〜1-11、5-46〜5-47 |

## PSRTTY側

- 無線機設定の送信方式をProfileごとにFSKへ切り替えます。既存のAFSK設定は保持します。
- CATは既存のHamlibを使用。FSK用には別COMを明示指定します。CATのCOMや「無線機と共用」は使用できません。
- FSK専用COMのDTRまたはRTSでITA2を出力します。音声出力ストリームは開きません。Audio INは従来どおりです。
- PSRTTYのモード表示RTTY / RTTY-RはHamlibのRTTY / RTTYRに対応し、無線機ではFSK / FSK-Rとなります。SSBのDATAモードではありません。
- 送信前にモード設定と読返しを確認し、失敗した場合はPTTを開始しません。
- 外部PTTを同じFSK専用COMで使う場合は、別信号線・役割PTTに限ります。STOP／例外時に解除します。

## TS-890SのUSB設定例

| 用途 | COMと設定 |
| --- | --- |
| CAT | 仮想Standard COM。Menu 7-01のボーレートを合わせる |
| FSK | 仮想Enhanced COM。CATと異なるCOMをPSRTTYのFSK出力に指定 |
| DTRでキーイング | Advanced 20 = RTTY Keying、19 = Off |
| RTSでキーイング | Advanced 19 = RTTY Keying、20 = Off |
| Standard側の信号 | Advanced 17 = Flow Control、18 = Off。CATでPTTする設定例 |
| PTT | CAT（送信TX;／受信RX;）。USBのPTT信号を追加割当しない |

RTTY Keyingは1本の信号にだけ割り当てます。StandardとEnhancedはCOM番号の大小から判断できません。Windowsのデバイスマネージャーで「場所のパス」末尾（1）= Standard、（2）= Enhancedを確認します。YaesuのEnhanced CAT／Standardキーイングの説明を転用しません。

USBのRTTY Keyingを有効にするとACC2のRTTY入力は無効になります。ACC2を使用する場合はUSB RTTY Keyingを解除し、外部FSKインターフェース用COMを指定します。

## シフト・トーン・極性

| 機種 | シフト | 極性 | Markトーン |
| --- | --- | --- | --- |
| TS-590SG | Menu 50 = 170 Hz | Menu 51 | Menu 52 = 2125 Hz |
| TS-890S / TS-990S | Menu 2-06 = 170 Hz | Menu 2-07 | Menu 2-08 = 2125 Hz |

メーカー資料ではACC2の極性Offは2番ピンをGNDへ短絡してMark、OnはSpaceです。RS-232変換・トランジスター等のインターフェースによって論理は反転し得るため、ソフト側のDTR/RTS ON/OFFと同一視しません。無線機の極性とPSRTTYの極性反転を確認してRYテストで合わせます。RS-232の電圧をACC2へ直結しないでください。

TS-590SGとTS-990SのUSBケーブルはCAT・音声用に利用できますが、これだけで外部FSKキーイング入力を代替しません。受信Audio INはUSB Audioまたは適切な外部音声入力を使用します。外部PTTはACC2 13番SS／12番GNDを利用できます。

## 対応範囲・検証

選択肢のKenwood 3機種すべてへ機能と8言語の説明を追加しました。直接FSK非対応として除外したKenwood機種はありません。ただしTS-590SG／TS-990Sは外部インターフェースが必要です。

Windows実機、Hamlib DLLと各無線機の組合せ、USBドライバー、実際のキーイング波形・極性は未検証です。メーカーPDFとウェブサイト用PHPは差分ZIPに含めません。
