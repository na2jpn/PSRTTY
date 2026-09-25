# PSRTTY Ver0.83 正本

このZIPがVer0.83のソース正本です。単独で展開でき、過去の差分・FIXの適用は不要です。
今後は PSRTTY_0.83_CANONICAL_SOURCE.zip だけを開発基準としてください。
0.79や0.81／0.82の差分・FIXから再構築しないでください。

START_HERE.md → HANDOFF.md → TIME_POLICY_078.md の順に読んでください。
設定・運用ログ・ビルド済みEXEは含みません。既存の運用データを削除する必要はありません。

## 0.83のクロススコープ
コントロール右のボタンで別ウィンドウを表示。各方向で最新＋1つ前の2本（最大4本）を保持し、前の輪は薄く描きます。残光は取得時刻から最大0.7秒。同調時は線に近い楕円です。
受信位置変更・入力停止・非表示で残光を消去します。解析は5 Hz、フェード描画は20 Hzです。

## Windowsビルド
python -m unittest discover -v
その後 build-windows.ps1 を実行。配布ZIPは release/PSRTTY_0.83.zip。

現行仕様はHANDOFF.md、VERSION_083.md、TIME_POLICY_078.md。docs/history配下は過去の記録であり、追加適用の指示ではありません。
