# PSRTTY 1.09 ウィンドウ修正の検証

2026-10-08（JST）。基準: PSRTTY_1.09_FULL_SOURCE.zip。

- 対象: ダイレクト送信、クロススコープ、コントロール、サブデコ、ショートカットキーガイド。
- 全508テスト: 失敗0、エラー0、1件スキップ（64.634秒）。スキップは既存のインストール別ローカルソケット検証で、OS側の制約です。
- 関連34テスト成功。新規6テストで、5画面のネイティブ所有者なし・前面固定フラグなし・非モーダル、メインを選んでも表示／処理継続、位置保存、メイン終了時の全画面終了、フォーカス呼び出し、英語タイトルと既存スタイル保持を確認。
- 実際のQtキー入力で、ダイレクト画面からCtrl+F12で閉じ、メインからShift+F12で開き、入力欄へフォーカスすることを確認。
- Windowsの所有関係を作るQWidget親を外し、アプリ参照はself.mainで保持。メイン終了時の明示的な画面終了処理は継続使用。クロススコープの保存先もself.mainへ変更。
- 版番号1.09、公開日2026-10-08を維持。利用者向け更新履歴は1.09の変更に統合し、FIX番号は記載しません。日英更新履歴と詳細資料を更新。
- Python構文、差分適用後の全ファイルSHA-256一致、ZIP CRCを確認。無線機・音声・ADIFの実装は変更していません。

Linux／Qt offscreenでの検証です。Windows実機の前後関係とタスクバー表示、Windowsビルド、実無線機・音声装置での確認は未実施です。裏へ回る際にhide()やclose()を呼ばず、通常のOSウィンドウ切り替えへ委ねる構成です。

## English
All 508 tests passed with one existing environment-related local-socket skip. The 34 focused tests passed. Six new tests verify independent native ownership, normal stacking flags, non-modal operation, retained background activity/appearance, saved position, recall and shutdown. Actual Qt key events verified Ctrl+F12/Shift+F12 close/open and editor focus. Version/date remain 1.09 / 2026-10-08. Real Windows stacking/taskbar behavior, Windows builds and radio/audio hardware were not tested. Changes remove the native owner without hiding or stopping the windows when the main window is selected.
