# PSRTTY 0.86 検証

2026-09-27 / Python 3.12 / Linux Qt offscreen。

`QT_QPA_PLATFORM=offscreen python -m unittest discover -v`：258件実行、257件成功、既存1件スキップ。詳細は `docs/validation/tests86.txt`。

更新履歴の先頭が0.86、0.83が初公開と表示されること、履歴画面のスクロール、C同調とクロススコープ間の余白、SQ表記、交信済みバンド表示の親が「現在のQSO」であることをoffscreen画面とウィジェット状態で確認。

この実行環境には日本語フォントがなく、スクリーンショットの日本語が四角として描画されるため、日本語文字の見た目はWindowsで確認してください。0.86のWindows EXEビルド・実機での送受信は未実施です。送信音声処理は変更していません。
