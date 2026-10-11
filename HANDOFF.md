# PSRTTY 1.15 引継ぎ

基礎: 1.14正本 SHA-256 97a1f978e8dad2087baac03553820858c521db6f9f71b0030b5bc25717d05565。
正本日付: 2026-10-12。FIX1～FIX4を統合したフルソースです。
バージョンは psrtty/__init__.py が中心です。Configも同じ変数を使用します。

変更と検証: VERSION_115.md、docs/VALIDATION_115.md。
Audio IN個別保存で再適用しますが、Windows実機の入力問題の原因を断定していません。
TX中のALC開始前は開始線までの85%を水色で表示します。実測した余裕量ではありません。SWR/PWRの最終TX値は2秒保持。
SWR/PWRの変換仕様と未対応機種: docs/METERS_115.md。
zLog/Z-Server、ダイレクト送信の仕様は1.14を維持します。
