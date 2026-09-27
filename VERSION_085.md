# PSRTTY 0.85

## 適用
PSRTTY_0.84_CANONICAL_SOURCE.zipを展開したソースへ、PSRTTY_0.85_DIFF.zipの内容を上書きしてください。
設定・ログ・EXEを含まないソース差分です。Windowsでbuild-windows.ps1を実行し、release/PSRTTY_0.85.zipを生成します。

既存の編集済みマクロは自動上書きしません。新しいコンテスト文面を使うには、マクロ編集でテンプレートを選び［反映］→［保存］してください。

## 取得とQSO欄
- CALL自動取得の隣に「CQのみ」。初期ON、状態保存。CALL取得だけをCQ単語のある文に限定します。
- 自動取得OFFならCALL/RST-R/RCVDとも自動更新しません。カードクリックはチェック状態に関係なく解析します。
- DEの直後、TUの直後、CQの後の一意なコールを優先。自局を候補から除外します。
- 「JF3DCH 599 18 18」のような宛先＋交換番号ではCALLを変えず、RST-R/RCVDだけ更新します。
- 複数の局名だけが並び送信局を判断できない文ではCALLを更新しません。復号誤りから意図を完全には復元できないため手修正は可能です。
- 受信番号の前のハイフンは除去し、599 -25を25として取得。CQ WWの州・地域略号の取り込みを維持します。
- CALLの小文字入力・貼り付けは大文字に自動変換。
- 「周波数変更でクリア」は初期OFF、状態保存。CALL取得・入力時の無線機周波数から絶対差20Hz以上でCALL/RCVDを空に、RST-Rを599に戻します。5Hzずつ動かしても基準から20Hzに達した時点で実行。SENT/固定は保持します。
- 日時・日時手動の一式を右へ寄せました。

## マクロ
CQ WW RTTY／JARL World Wide RTTY共通：

|キー|送信内容|
|---|---|
|F1|`CQ TEST {MYCALL} {MYCALL} K`|
|F2|`{MYCALL} {MYCALL} {MYCALL}`|
|F3|`{HISCALL} 599 {SENT} {SENT} DE {MYCALL} K`|
|F4|`R TU 73 DE {MYCALL}`|
|F5|`AGN DE {MYCALL} K`|
|F6|`{HISCALL} NR NR?`|
|F7|`RRR DE {MYCALL} TEST`|
|F8|`KKK`|
|F9|空欄|

AutoCQはF1を使用。SENTはテンプレート反映時にCQ WW=25、JARL WW=01、固定ON（編集可）。

「通常交信短縮版（英文RTTY）」を通常交信の直下へ追加。反映時SENT空欄・固定ON。

|キー|送信内容|
|---|---|
|F1|`CQ DE {MYCALL} K`|
|F2|`{HISCALL} DE {MYCALL} K`|
|F3|`{HISCALL} DE {MYCALL} UR {RSTS} K`|
|F4|`TU 73 {HISCALL} SK`|
|F5|`RRR TU {HISCALL} DE {MYCALL} K`|
|F6|`AGN AGN`|
|F7|`MY QTH {MYJCCJCG} K`|
|F8|`KKK`|
|F9|空欄|

通常交信の既存文面は変更なし。マクロボタンのツールチップは変数展開済み全文を折り返して表示。横スクロールは採用していません。

## 交信履歴
最新QSOの上枠線に重ねて、CALLの交信履歴を表示。アプリが読み込むlogdata内の全ADIFを対象（コンテスト期間で絞り込まない）。BANDのみでFREQがないADIFも参照できます。
- 未交信：水色「初めての局です」
- 他バンドのみ：濃い水色「JX1XXX 21MHz 28MHz 交信済み」
- 現在バンドを含む：赤「JX1XXX 21MHz 28MHz 交信済み＊＊＊」
CALL空欄で消去。同一バンドは重複表示せず、CALL/周波数/アプリでのログ追加・編集に追従します。外部ソフトがADIFを書き換えた場合はログを再読込するか再起動してください。

## 設定とアンテナTUNE
- 設定画面を開く・キャンセル・×では接続と受信を維持。入力検証を通過した保存時にAutoCQ/TXを停止し、旧設定で切断処理を開始してから反映します。
- 接続中は別COM接続を作る「接続テスト」を実行しません。通常の保存後は手動再接続。既存の設定画面内「接続」は保存して接続する動作を維持します。
- コントロール画面に「アンテナTUNE」を追加。今回のコマンド確認対象はIC-7300、IC-7300MK2、FT-991/FT-991A、FTX-1の内蔵チューナー。
- 状態取得成功・受信中・HF/50MHz範囲で有効。未確認の機種、未接続、外部チューナー/ATAS選択では無効。外部チューナーの選択を勝手に変えません。
- TUNE中はマクロ/AutoCQを抑止。完了状態を監視し、STOP・切断・終了・タイムアウトで停止要求します。実機動作確認は未実施です。

コマンド確認資料（メーカー作成）：
- ICOM IC-7300補足説明書、1C 01 02：https://mackey.my.coocan.jp/images/IC-7300_JPN_Supp_7.pdf
- ICOM IC-7300MK2 CI-V Reference Guide：https://icomuk.co.uk/files/icom/PDF/productAdditionalFile/IC-7300MK2_ENG_CI-V_0.pdf
- YAESU FT-991 CAT（AC002;）：https://www.yaesu.com/Files/4CB893D7-1018-01AF-FA97E9E9AD48B50C/FT-991_CAT_OM_ENG_1612-D0.pdf
- YAESU FTX-1 CAT（AC003;）：https://connect.yaesu.com/indivisual/wp-content/uploads/2025/11/FTX-1_CAT_OM_JPN_2512-D.pdf

## C同調
メイン画面のクロススコープ横に「C同調 +10.0 Hz」。受信MARK/SPACEの中点と設定センターの差（＋は受信音が高い）。RFダイヤルの回転方向を示す符号ではありません。
安定した両トーンの周期を測定。約0.5秒の測定値を平滑化し、333msごとに表示。0.1Hz表記は実受信の精度保証ではありません。

|ずれの絶対値|文字色|
|---|---|
|5Hz未満|青|
|5以上9未満|濃い緑|
|9以上11未満|黄緑|
|11以上15未満|黄色|
|15以上20未満|オレンジ|
|20以上25未満|朱|
|25以上・判定不能・無信号|黒「C同調 -」|

境界は表示値（小数1桁）で統一。負のゼロを表示しません。片側トーンだけの待機信号・弱い信号・混信で安定区間がない場合も数値を出しません。
既存クロススコープの残光0.7秒、最新＋前1本/各軸、描画処理とデコーダーは維持しています。
