# PSRTTY 1.09 正本化検証 / Canonical verification

2026-10-08（JST）。PSRTTY_1.08_FULL_SOURCE.zipを基準に1.09の実装・修正をすべて統合。過去の差分ZIPの追加適用は不要です。

- 全527テストを再実行: 失敗0、エラー0、既存の環境制約によるローカルソケット1件スキップ（67.822秒）。実行ログ: docs/TEST_RESULTS_109_CANONICAL.txt。
- Linux / Python 3.12 / PySide6 6.11.2、Qt offscreenで検証。Windows EXEのビルド・実行、実無線機、SCU-17／CATケーブル、実音声デバイス、Windowsタスクバー・ウィンドウ前後関係・キー競合は未確認です。
- 初期設定ガイドの「受信・チューニング」内、「波形の高さと入力音量」に続けてRXゲージの色・表記・音量調整方法を日英で追加。両言語をQtで描画し、表・折り返し・スクロールと表示の収まりを目視確認。
- RXゲージは灰0～5%（文字なし）、水色6～29% Low、緑30～79% Good、黄80～89% High、赤90%以上 Over!。Audio INと同じ平滑化済み表示です。受信音量・デコーダーの変更はありません。詳細: docs/VALIDATION_109_FIX3.md。
- 常用5画面の独立ウィンドウ、ダイレクト送信、アイドル対応、旧機種／外部PTT対応、既存設定・プロファイル・交信記録の処理を維持。
- メインタイトル／Aboutは共通psrtty.__version__の1.09。ADIF生成・パッケージ出力も共通版を使用。更新履歴は日英とも2026-10-08 Ver1.09に統合し、利用者向けにFIX名やサンクス変更を追加していません。
- ICOのQt pixmap読み込み、アプリ／メイン／Aboutでの共通アイコン利用、AppUserModelID、PyInstallerのICO同梱とICO指定、build-windows.ps1の1.09とrelease/PSRTTY_1.09.zipの出力指定を確認。
- ソース構文、ガイドへの日英掲載位置と表の全項目、ZIP CRC、ZIPから読み戻した全ファイルSHA-256を確認。設定／ログのconfig・logdata・varは空のまま。__pycache__や個人データを含めていません。
- 初回1.09と各修正時点の検証資料は過去の記録として残しています。最新の正本化検証はこの資料です。

## English
This canonical archive integrates all 1.09 implementation and corrections based on the 1.08 canonical source. No earlier patches are needed. The complete 527-test suite passed with no failures/errors and one existing environment-related skip. Japanese/English RX gauge tables and adjustment instructions were added immediately after Waveform height and input level, rendered and visually checked. Version 1.09, history date, ICO loading, AppUserModelID and Windows packaging settings were checked. Audio gain and decoder behavior remain unchanged. ZIP CRC and all archived SHA-256 hashes were verified. Real Windows builds, stacking/taskbar/shortcut behavior and radio/audio hardware testing remain outstanding. Earlier validation files describe earlier source states.
