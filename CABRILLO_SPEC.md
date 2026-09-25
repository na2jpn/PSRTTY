# Cabrillo出力仕様（Ver0.76）

確認日：2026-09-24。Cabrillo 3.0、ASCII、CRLF、日時UTC、モードRY。

## 根拠資料

- WWROF Cabrilloヘッダー仕様: https://wwrof.org/cabrillo/cabrillo-v3-header/
- WWROF QSO仕様: https://wwrof.org/cabrillo/cabrillo-qso-data/
- CQ WW RTTY出力例: https://cqwwrtty.com/cabrillo.htm
- CQ WW RTTY現行規則: https://cqwwrtty.com/rules.htm
- JARL WW RTTY規約: https://www.jarl.org/Japanese/1_Tanoshimo/1-1_Contest/rtty_rule.html
- JARL英語規約: https://www.jarl.org/English/4_Library/A-4-3_Contests/rtty_rules_en.html
- DXLog開発元の対応大会一覧: https://dxlog.net/sw/contestlist.php

JARL規約はCabrilloを推奨するが、参照ページにCONTEST識別名とQSO列例はない。
CONTESTのJARL-WW-RTTYはDXLog開発元の対応表と照合。
JARLのQSO列はCabrillo基本列＋規約のRST/年齢から構成した。主催者サーバー受理は未確認。
CQ WWの列は主催者の公開例と照合。空白区切りは同ページが許容。
CQ WWヘッダー紹介ページと現行規則に差があるYOUTH等は現行規則を優先。

## 形式

| 形式 | CONTEST | 交換番号 | 対象バンド |
|---|---|---|---|
| 汎用 | 利用者が指定 | 利用者が並び指定 | Cabrillo候補から選択 |
| JARL WW RTTY | JARL-WW-RTTY | RST＋年齢/01（00/99可） | 80/40/20/15/10m、ALL部門 |
| CQ WW RTTY DX | CQ-WW-RTTY | RST＋CQゾーン＋州/地域/DX | 80/40/20/15/10m |

汎用の初期並び：FREQ MODE DATE TIME MYCALL RSTS SENT HISCALL RSTR RCVD。
JARLは同じ列で交換番号が年齢。CQ WWはSENT/RCVDをゾーンとQTHに分割する。
HF周波数はkHz、VHF以上はCabrillo帯域トークン。QSO/X-QSO両対応。
CQ MULTI-ONE/TWOはTX番号0/1必須、一覧で入力/まとめて設定。
米国・カナダのQTH欠落は検出する。接頭辞だけで確定できない移動運用等は明示DXで補正可能。
JARLの年齢は1～3桁、1桁は2桁へ補い、00/01/99を保持。

## 画面と保存

1. 形式選択。
2. 年・期間・JST/UTC・自局CALL・バンド抽出、QSO選択と出力専用編集。
3. 自局・参加区分・送信機区分・運用形態・運用地・運用者・オーバーレイ、氏名/メール/住所/国、クラブ、得点、休止時間、コメント等。
4. 件数/条件・確認事項・本文プレビュー、保存、保存先フォルダー表示。

必須/条件付き項目はエラー表示、氏名/メール/住所の未入力は確認事項として表示。
YOUTH/ROOKIEの生年月日/初免許日はSOAPBOXへ出力。資格要件の自動判定はしない。
JARL移動運用はLOCATIONへ都道府県、マルチオペはOPERATORSを入力。
CLUBには正式名称、JARL登録クラブ番号等の補足はSOAPBOXを利用できる。
住所は1行45文字/6行、氏名75文字、SOAPBOXは75文字で折返し。
得点は利用者の任意入力。重複QSOは警告し、自動削除しない。

入力は戻る/検証エラー/保存失敗で保持。再読込による編集破棄は確認する。
元ADIFは読み取りのみ。出力用に編集した周波数・日時・交換番号等は元ログへ書き戻さない。
同一フォルダーの一時ファイルからos.replaceで確定し、途中失敗で既存ファイルを壊さない。
ADIF、生ログ、バックアップ名への保存を拒否。既存出力上書きはOS保存ダイアログで確認。
作成するのは提出用ファイルまで。アップロード・送信、得点/マルチ集計は実装範囲外。

## 0.76の画面精度

日時は分単位表示・入力、抽出境界は開始00秒～終了59.999999秒。未編集QSOの内部秒は保持。
大会期間は現在の開催ルールによる計算値であり、公式発表の確認ではない旨を青字で表示。
