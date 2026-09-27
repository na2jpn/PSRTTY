# PSRTTY 1.01 正本検証

- 2026-09-27、提供された Hamlib 4.7.2 の Windows x64 ZIP とソース tar.gz を、公式リリース掲載 SHA-256 と照合した。
  - `hamlib-w64-4.7.2.zip`: `8553bc6c5c6032e8debf99c017e98f58fed7e07e7c25d04815dc3e8bbe3304c7`
  - `hamlib-4.7.2.tar.gz`: `ae1fcf2dbc80ea0786ea8f047b09399c3f7737d1930442f61a031708ed33e88f`
- Hamlib 4.7.2ヘッダーの7機種のモデルID、CAT APIの引数型、Windows DLLの直接依存関係を確認した。`libgcc_s_seh-1.dll` は配布対象のDLLから参照されていないため同梱しない。
- `lib/hamlib/` にはHamlib本体、libusb、winpthreadsのDLL、Hamlib対応ソース、関連ライセンスと通知を置く。実行時は外部DLLを読み込み、同じフォルダーの互換DLLへ交換できる。
- 1.01以降の画面内更新時、これらのファイルをmanifestで検証し、失敗時に復元するテストを含む。
- Linux上のQt offscreenで全テストを実行。298件実行、成功297件・スキップ1件。Windows実DLLはこのテストでは呼び出していない。

## 実機検証の範囲

Windows EXEのビルド、Windows上の実DLL読込、対象無線機とのCAT・PTT、外部機器RTS/DTRの実動作はこの環境では未確認。各機種は試験対応として扱う。提出用Cabrilloは保存後に内容を確認し、主催者の提出画面から送信する。

## 更新手順

旧0.88の更新画面はEXE以外を含むZIPを受け付けないため、1.01への移行は配布用ZIPの上書きです。配布ZIPには設定・ログの空フォルダーのみ含めます。1.01以降のZIPは`var/versionup.json`で追加ファイルを宣言し、manifestのSHA-256一覧と一致する場合のみ更新します。Windows上の実行ファイル上書きと実機動作は未確認です。
