# PSRTTY Ver1.06 引き継ぎ

唯一の基準はこのフルソースです。Ver1.05 VerFIX正本から実装しました。ソースは1.06、ビルドスクリプト・About・ADIF版情報も1.06です。Windows配布用ZIPはbuild-windows.ps1で作成します。

1.06対象：画面外復帰（タイトルバー・外枠込み）、Hamlib FT-991/FTX-1の受信幅・DNR・NB、保存式Language、表示設定の単一チェック、Aboutの罫線＋左ロゴ／右文章、HAMLOG-CSV、FreeBSD対応パッチ。

HAMLOG CSVは15列、CP932、CRLF、ヘッダーなし、JST時刻末尾J。送信RST→受信RST。Remarks1=SENT/RCVD、Remarks2=選択式MYCALL。未記録の所在地・QSL・DXは推測せず空欄。期間→自局CALL→バンド→対象交信選択の既存操作を使用します。

英語表示は主要メニュー・操作画面を対象とし、長文ガイド・更新履歴・配布条件は日本語原文を保持しています。実機試験とWindows EXEビルドは未実施です。FTX-1のNARROW操作は未対応状態で維持し、Hamlibの幅指定で制御します。

既存設定・マクロ・ログを配布物で上書きしない方針を維持します。FreeBSD提案パッチ原文をdocs/contributionsに保管しています。

FIX1：MainWindowでトップレベルメニューを保持。test_v106は連続取得を分割し、GC後のメニュー有効性も検証。版番号は1.06。
