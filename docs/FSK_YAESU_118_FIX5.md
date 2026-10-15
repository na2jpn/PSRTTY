# Yaesu FSK — 1.18 FIX5

2026-10-15。選択できるYaesu 13項目をメーカー取扱説明書に基づいて分類。FSK対応10項目（既存FT-891を含む）、AFSKで運用する3項目です。メーカー標準仕様を根拠に通常の対応機能として案内し、実機検証の記録は開発資料で管理します。

## 接続と機種別設定

| 選択肢 | 接続 | 無線機側の設定 |
| --- | --- | --- |
| FTX-1 Field / Optima | 本体USB Enhanced COM=CAT、Standard COM=FSK | MODE RTTY：RPTT SELECT、MARK FREQUENCY=2125 Hz、SHIFT FREQUENCY=170 Hz、POLARITY TX=NOR |
| FT-710 | 本体USB Enhanced COM=CAT、Standard COM=FSK | MODE RTTY：RPTT SELECT、MARK FREQUENCY=2125 Hz、SHIFT FREQUENCY=170 Hz、POLARITY TX=NOR |
| FTDX10 | 本体USB Enhanced COM=CAT、Standard COM=FSK | MODE RTTY：RPTT SELECT、MARK FREQUENCY=2125 Hz、SHIFT FREQUENCY=170 Hz、POLARITY TX=NOR |
| FTDX101D | 本体USB Enhanced COM=CAT、Standard COM=FSK | MODE RTTY：RPTT SELECT、MARK FREQUENCY=2125 Hz、SHIFT FREQUENCY=170 Hz、POLARITY TX=NOR |
| FTDX101MP | 同上 | 同上 |
| FT-991 / FT-991A | 本体USB Enhanced COM=CAT、Standard COM=FSK | 060 PC KEYINGとSHIFT PORTを別信号に設定。番号差は下表 |
| FTDX3000 | 本体USB Enhanced COM=CAT、Standard COM=FSK | 093=USB、065 PC KEYINGをFSKと反対の信号。095=NOR、097=170 Hz、098=2125 Hz |
| FT-891 | 本体USB Enhanced COM=CAT、Standard COM=FSK | 10-05をFSK信号、07-12 PC KEYINGを反対の信号。10-07=NOR、10-09=170 Hz、10-10=2125 Hz、10-11=LSB |
| FT-950 | 外部FSKインターフェース→RTTY/PKT 6ピン | 4番FSK IN、2番GND。PTTは3番。062=170 Hz、063=2125 Hz、060=nor |
| FT-450 | 外部FSKインターフェース→DATA 6ピン | 4番FSK IN、2番GND。PTTは3番。D TYPE=RTTY、RTY SFT=170 Hz、RTY TON=2125 Hz、RTYTPOL=NOR |
| FT-817 / FT-817ND | AFSK | DATAのRTTY設定はAFSKであり、直接FSKキーイングへは切り替えない |
| FT-818ND | AFSK | 同上 |
| FT-857 / FT-857D | AFSK | 同上 |

PSRTTYのRTTY / RTTY-RはHamlibのRTTY / RTTYRを指定します。無線機ではRTTY-L / RTTY-U（RTTY-LSB / RTTY-USB）相当となります。FT-450はDATA系の表示・D TYPE=RTTYを使用します。モード読返しに失敗した場合は送信を開始しません。

| 項目 | FT-991 | FT-991A |
| --- | --- | --- |
| PC KEYING | 060 | 060 |
| RTTY SHIFT PORT | 098 | 096 |
| RTTY POLARITY-TX | 100 | 098 |
| RTTY SHIFT FREQ | 102 | 100 |
| RTTY MARK FREQ | 103 | 101 |

本体・説明書の版によって番号が異なる場合は項目名を優先します。表の値は設定例であり、無線機側メニューをソフトが自動変更する機能ではありません。

## USB信号とPTT

FSKとPTTには別の信号を割り当てます。FSK=DTRならPTT側=RTS、FSK=RTSならPTT側=DTRを表示。FT-891／FT-991(A)の接続章にはPC KEYINGとRTTY-SHIFTの対応表があり、FTDX3000にも反対の信号を指定する説明があります。RPTT SELECTを持つ機種では、この設定はPTT側です。FSK入力選択と混同しません。

CATはEnhanced COM、FSKはStandard COMを明示指定し、CATとのCOM共用は許可しません。Standardを第二CATとして同時に開きません。COM番号の大小から役割を推測しません。

PTT方式CATを使う場合も、FSK信号を無線機側PTTへ割り当てないよう案内します。外部PTTをFSK専用COMで共用する場合は、別信号線・役割PTTに限り、一つのハンドルで制御します。

## 外部インターフェース

FT-450／FT-950は、SCU-17または適合するFSKインターフェースのCOMを使います。SCU-17のStandard COMを指定し、標準設定はFSK=DTR／PTT=RTS。内部S1001で入れ替え可能なので実際の位置に合わせます。機種に適したケーブルでFSK INとGNDへ接続します。

一般的な音声用DigirigケーブルやUSB Audio OUTはFSK出力を代替しません。RS-232の電圧を無線機へ直結しません。Audio INは従来の受信音声入力を使用し、FT-891はUSB音声を内蔵していないため、受信音声を別途接続します。

## メーカー資料

- [FT-891 取扱説明書](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-891_Advance_Manual_ENG_1806-F.pdf)
- [FT-991 / FT-991A 取扱説明書](https://www.yaesu.com/jp/manuals/yaesu_m/FT-991_OM_JPN_EH057M003.pdf)
- [FTX-1 取扱説明書](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FTX-1_OM_ENG_EH084M201_2506E-DS.pdf)
- [FT-710 取扱説明書](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-710_OM_ENG_EH080H201_2307N-GS.pdf)
- [FTDX10 取扱説明書](https://yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FTDX10_OM_ENG_EH076H202_2307A-LS-1.pdf)
- [FTDX101D 取扱説明書](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FTDX101MP_D_OM_ENG_EH068H215_2406R-US-1.pdf)
- [FTDX101MP 取扱説明書](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FTDX101MP_D_OM_ENG_EH068H215_2406R-US-1.pdf)
- [FTDX3000 取扱説明書](https://yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FTDX3000_OM_ENG_EH046H204_1902M-DS-1.pdf)
- [FT-450 取扱説明書](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-450_OM_ENG_EH024H102.pdf)
- [FT-950 取扱説明書](https://www.yaesu.com/jp/manuals/yaesu_m/FT-950_J2.pdf)
- [FT-817 / FT-817ND 取扱説明書](https://yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-817_OM.pdf)
- [FT-818ND 取扱説明書](https://yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-818ND_OM_ENG_E13772004_2003u-ES-1.pdf)
- [FT-857 / FT-857D 取扱説明書](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-857D_OM_ENG_EH007M108.pdf)
- [FT-991A 取扱説明書](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-991A_OM_ENG_EH067M205_2111A-KS-1.pdf)
- [SCU-17 取扱説明書](https://www.yaesu.com/jp/manuals/yaesu_m/SCU-17_OM_ENG_JPN.pdf)

主な参照箇所：FTX-1英語版52〜54頁、FT-710 56〜58頁、FTDX10 64〜66頁、FTDX101 68頁のRTTY章、FTDX3000 105頁、FT-891詳細編63頁、FT-991A英語版121頁、FT-450 72頁。各CAT説明書のEnhanced／Standardの役割も確認。メーカーPDFはZIPへ転載しません。

実機検証・Windowsビルドの状況は VALIDATION_118_FIX5.md に記録します。

### USB仮想COMの役割を確認したCAT資料

- [FTX-1 Advanced Manual — MODE DATA / CAT](https://yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FTX-1_AM_ENG_2506-B.pdf)
- [FT-710 CAT Operation Reference Manual](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-710_CAT_OM_ENG_2306-C.pdf)
- [FTDX10 CAT Manual](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FTDX10_CAT_OM_ENG_2308-F.pdf)
- [FTDX101 CAT Manual](https://www.yaesu.com/jp/amateur_index/product/ftdx101/FTDX101_CAT_OM_JPN_2308-J.pdf)
- [FT-991A CAT Manual](https://yaesu.com/jp/manuals/yaesu_m/FT-991A_CAT_OM_JPN_1612-C.pdf)
- [FTDX3000 CAT Manual](https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FTDX3000_CAT_OM_ENG_2006-D.PDF)

### 補助的な一次資料

[ARRL QST 2021年6月号 FTDX10実機レビュー（著者Steve Ford, WB8IMY、41頁）](https://conspark.com.pl/files/resources/FTDX10%20Product%20Review%20%28June%202021%20QST%20-%20ARRL%29.pdf)も照合。RPTT SELECT=RTS、FSK=DTRでの運用を記載しています。メーカー説明書のRPTT SELECTはPTT制御の説明であり、FSK入力選択と同一視しません。现代機の表は別信号を割り当てる設定例です。
