PSRTTY 1.29 フルソース — 2026-10-23

1.28（2026-10-22）の再正本をベースに、RYスキマーのSciPy同梱不足対策を実装。
過去の差分を適用する必要はありません。Windowsビルドは build-windows.ps1。

SciPyのarray_api_compatが_external側／_lib側のどちらにあっても、NumPy・common
モジュール群を収集。fft・linalgの収集を確認し、不足時はビルドを停止します。
Torch、CuPy等の不要な計算バックエンドを一括導入するものではありません。

完成したdist/psrtty.exeに --self-test-skimmer を渡し、空の作業フォルダーで
ストリーミングFIRと2局の模擬IQ信号からのコール・レポートの復号を検査します。
成功報告・終了コード・EXEの版・frozen属性を確認してからrelease ZIPを作成。
検査には無線機・ExtIO DLL・音声機器は必要なく、CAT/PTTや送信は行いません。

var/updatesはZIP1世代、var/backupsはZIP2世代を保持。
logdata/backupsはログZIP3個、編集前BAKを月別ADIFごとに3個保持。
現在の交信ログ・送受信記録本体、月移動復旧フォルダー、不明ファイルは保持。
Windows実機でのIC-7610接続・IQ受信は利用者側の確認が必要です。
検証結果は docs/TEST_RESULTS_129.txt を参照してください。
