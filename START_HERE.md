# PSRTTY Ver1.14 フル実装ソース（2026-10-10）

1.13正本に1.14の全変更を統合したフルソースです。差分の追加適用は不要です。

Windowsでは展開先で `build-windows.ps1` を実行してください。
8言語検査・全テスト・EXEビルド・配布ZIP検査後、`release/PSRTTY_1.14.zip` を生成します。
このフルソースZIP自体はアプリ内更新用ZIPではありません。

主な変更: ダイレクト待機LTRS、自動STOP 1～9秒（初期2秒）、Z-Server経由のzLogリアルタイム連携。
zLog連携は初期OFF。通常TCPでZ-Serverを起動し、zLogとPSRTTYを同じサーバへ接続してください。
既存の設定・プロファイル・マクロ・ログ・8言語・世界のRTTY周波数ガイドを継承します。
利用者のconfig・logdata・varは含めません。既存データを削除しないでください。

仕様: docs/VER114_JA.md。検証: docs/VALIDATION_114.md。
Git用リリースノート: docs/RELEASE_NOTES_114.md。
初期設定ガイドの連携ページにも説明があります。docs/INTEGRATION_114_*.htmlは8言語の同内容です。
過去版の資料は当時の履歴です。旧zLogのファイル連携説明はADIF出力用途として参照し、現在の設定には1.14の案内を使ってください。
WindowsのzLog/Z-Server実アプリと無線機による確認は未実施です。
