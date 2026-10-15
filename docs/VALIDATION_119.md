# PSRTTY 1.19 検証記録 — 2026-10-15

## 修正対象

FSK送信開始時のモード再設定によるフィルター変更。
ICOMではFIL1の固定指定を削除。同じRTTY／RTTY-RならCI-V 04で確認して設定書込みを省く。
Yaesu・KenwoodのHamlib経路でも同じモードならrig_set_modeを省く。
切替が必要な場合はICOMでフィルター指定を省略、Hamlibでは従来の帯域幅変更なし指定を使用し、モードを読返して確認する。

## 実行結果

- ICOM修正時点で開始した全体テスト：881件、失敗0、環境依存スキップ1。319.328秒。
  QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
- 全体テスト実行中にYaesu・Kenwoodも修正。その最終実装を新しいプロセスで確認：関連22件すべて成功。2.437秒。
  tests.test_v119 / tests.test_v118.FSKModeTests / tests.test_v118_fix3.CapabilityTests /
  tests.test_v118_fix4.KenwoodFSKTests / tests.test_v118_fix5.YaesuFSKTests
- 新しい回帰テスト：ICOM対応32項目の各RTTYモードとFIL1～FIL3で、繰り返し送信開始してもモード設定書込みがないこと。
- Yaesu10項目・Kenwood3機種のRTTY／RTTY-Rと帯域幅250・500・2400で、繰り返し開始してもモード再設定がないこと。
- モード切替時のパラメーター、読返し不一致と読取り失敗時の中止を確認。
- 8言語、各1313項目の検証と英語フォールバック再生成：成功。
- 各言語は1.19履歴の追加のみ。既存の全訳文・旧履歴を保持。
- Pythonコンパイル：成功。
- 今回の全体テストでは終了待ちタイムアウトなし。

## 範囲

Linux / Python 3.12 / PySide6のオフスクリーン環境で実行。
スキップはOSのローカルソケット作成制限によるIPCテスト。
無線機の実動作とWindows EXEビルドはこの環境では実施していない。
WindowsではFIL2／FIL3を選び、CQの繰り返し送信で保持を確認する。
RTTY／RTTY-R間の切替は機種ごとの記憶フィルター動作にも従う。
