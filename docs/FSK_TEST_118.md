# 1.18 FSKキーイングの実機テスト

まずIC-7300で確認し、その後FT-891へ進めます。FSKは試験機能です。
既存の運用Profileを残し、別のProfileで試すとAFSKへ戻しやすくなります。

## IC-7300

1. USB接続・ドライバーと、従来のCI-V接続を確認します。
2. 無線機側の SET → 外部端子 → USB SEND/キーイングで、USBキーイング（RTTY）をDTR、USBキーイング（CW）をOFFにします。
3. PTTをCI-Vにする場合はUSB SENDをOFFにします。PTTをRTSにする場合はUSB SENDをRTSにします。DTRをPTTへ重ねて割り当てません。
4. 無線機のRTTYシフトを170 Hz、Markを2125 Hzに合わせます。受信音のMark/Space設定もPSRTTYと合わせます。
5. PSRTTYの無線機設定でIC-7300を選択し、「FSKキーイングモードに切り替える」→説明を確認→はい。
6. FSKキーイング出力で「無線機のCI-V接続を共用」、DTRを選択します。極性反転は初めはOFF。
7. 高度な設定（FSKモード）はRTTY、45.45 baud。AFSK用のLSB-D設定は保持されます。
8. Audio INは従来の受信入力を指定します。FSKでは送信用Audio OUTも第二Audio OUTも使いません。
9. 保存後に無線機を接続します。設定を変えたままの旧接続でテストせず、保存済み設定で接続し直してください。
10. ダミーロード・低出力で、まずRYテストまたは短いマクロを送信。RTTY表示・出力・別受信機での復調を確認します。設定画面のRYテストは最大10秒、途中STOPも可能です。
11. Mark/Spaceが逆ならFSK出力の極性反転を確認します。RTTY-Rと反転を同時に変更せず、一つずつ試します。
12. STOP・ウィンドウ終了・無入力自動STOPで送信が止まることを確認します。マクロとダイレクト送信も個別に確認してください。

CI-VのCOMを別途FSK用として二重に開く必要はありません。共用を選ぶと既存の接続を使います。
無線機のUSBキーイング設定はPSRTTYから自動変更しません。

## FT-891

- CATはEnhanced COM、FSKはStandard COMを明示指定します。同じCOMは指定できません。
- 10-05 RTTY SHIFT PORTをPSRTTYのキーイング信号（例：DTR）に合わせます。
- 本版の標準構成はCATによるPTTです。Standard COM側のRTTY PTT設定をキーイング信号と重ねないでください。
- 無線機はRTTY系モード。シフト・Mark周波数・極性を合わせます。
- FT-891にはUSB Audioがないため、受信音はSCU-17などの音声機器からAudio INへ接続します。
- IC-7300同様、短文・STOP・マクロ・ダイレクト送信を順に確認します。

## 確認結果を知らせる際

Windowsのバージョン、無線機、CI-V/CATとFSKのCOM設定、キーイング信号、PTT方式、極性、無線機のRTTY設定、表示されたメッセージを記録してください。
「キーイングの遅延」で止まる場合、まずPC負荷を下げて再確認します。遅延検出を無効にして送信を続ける機能はありません。

## 参照資料

- アイコム「Tips for the USB port settings」：IC-7300のUSB SENDとUSBキーイング（RTTY）のDTR/RTS割当。
  https://www.icomjapan.com/support/manual/2574/
- 八重洲無線「FT-891 Advance Manual」：RTTY USB接続、Standard COM、10-05 RTTY SHIFT PORT。
  https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-891_Advance_Manual_ENG_1806-F.pdf
