# PSRTTY 1.17 引継ぎ — 2026-10-15

フルソース: PSRTTY_1.17_CANONICAL_SOURCE.zip
仕様: VERSION_117.md。検証: docs/VALIDATION_117_CANONICAL.md。FIX1・FIX2統合済み。
バージョンの正本は psrtty/__init__.py。

Windows音量はpsrtty/windows_volume.py、UIはpsrtty/ui/windows_volume.py。選択endpoint IDと自プロセスのsessionだけを対象にし、ProfileにWindows音量を保存・復元しません。
外部PTTテストは設定画面のExternalPTTインスタンスで制御。各終了経路でOFF。通常送信は従来のtx_keying.pyを共有します。
手動モデルIDはEXTERNAL-MANUAL。CAT/CI-Vは一切使用せず、周波数不明で以前の無線機の周波数をログへ流用しません。
全QSO削除はlog_delete.py。ADIFのみ対象。原文ログ・既存バックアップは保持。バックアップ必須・検証後のみ移動、失敗時復元。
FT-950=1028、FT-450=1027。外部音声、RS-232C CAT（2stop/handshake None）。
Webガイドは別ZIP（63項目、8言語）。アプリのソースへ混在させません。
開発ルールdocs/DEVELOPMENT_RULES.mdを維持。サンクスは履歴・リリースノートに記録しません。

以下は1.16から引き継いだ既存仕様です。

# PSRTTY 1.16 正本引継ぎ — 2026-10-13

正本ファイル: PSRTTY_1.16_CANONICAL_SOURCE.zip
1.15最終正本を基に、1.16の機能とFIX1～FIX6をすべて反映しています。
中心バージョン変数は psrtty/__init__.py。公開日は2026-10-13。

- 周波数ポーリングは0.5秒。未完了要求は重ねず、メーターポーリングは維持。
- 接続時モードはLSB-D／USB-D／LSB／USB。自動切替ONは選択モードに従い、OFFは本体モードを変更しません。
- ADIF UDPは共通設定。初期OFF。QSOの保存成功後に1件送信し、ACK・自動再送はありません。
- 受信表示はメインのチェックと「デコード」の間で「逐次／まとめて」を選択。初期値は「まとめて」。選択保存、文字数による確定時の除外、途中切替の文字保持を実装。
- FT-891はHamlib 1036。USBはCAT用で、音声は外部接続。
- CI-VのUSB音声入力切替はIC-9700・IC-7300・IC-705のみ。初回ON、既存Profileは未設定ならOFF、コピーは設定を継承。実モードに対応した入力を読み返して確認します。
- UI・案内・履歴は8言語。受信表示とFT-891追加は独立した履歴項目。

開発ルールは docs/DEVELOPMENT_RULES.md を必ず確認してください。
仕様は VERSION_116.md、検証は docs/VALIDATION_116.md。
Windows EXEビルド、USB入力切替の無線機実機動作、FT-891実機動作、Log4OM2本体とのUDP相互運用はこの環境では未確認です。利用者から受信表示の動作確認OKの報告あり。
今後の開発はこの正本を基準にしてください。
