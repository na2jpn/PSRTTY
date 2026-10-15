# PSRTTY 1.18 正本引継ぎ — 2026-10-15

正本フルソース：PSRTTY_1.18_CANONICAL_SOURCE.zip。1.18のFIX1～FIX7を統合済み。差分の追加適用は不要。
バージョンの正本は psrtty/__init__.py。仕様 VERSION_118.md、履歴 CHANGELOG.md・UPDATE_HISTORY.txt・language/*.json のhistory.body。
Gitリリースノート docs/RELEASE_NOTES_118.md、検証 docs/VALIDATION_118_CANONICAL.md。

FSK本体 psrtty/fsk.py、機種別能力 psrtty/fsk_models.py、資料 psrtty/fsk_manuals.py。
設定 psrtty/ui/fsk_settings.py、機種別説明 fsk_help.py・fsk_yaesu.py、接続条件による色分けと短文 fsk_notice.py。
標準はAFSK。切替はProfile単位で、元のAFSK設定を保持。マクロ・Auto CQ・ダイレクト送信で同じFSK送信経路を使用する。
FSK対応45項目：ICOM32、Kenwood3、Yaesu10。直接FSK非対応23項目ではAFSKを案内。
USBケーブル1本で使用可能な16項目は黒、外部機器・別途音声接続が必要な29項目は青、直接FSK非対応23項目のみ赤。
FT-891はUSB CAT/FSKだが受信音声の別接続が必要なので青。USBケーブル接続の説明とSSBのUSBモードを混同しない。
無線機のUSB SEND／USB Keying等のメニュー名、デバイス名、USB／USB-DATA等のモード名は改変しない。

送信経路はMainWindow._send_textで方式を振り分け。AudioEngineの停止・スレッド管理とLiveTextの送信済管理を共有する。
FSKは音声出力を開かず、無線機接続・モード読返しを確認してからPTT。終了／失敗時に解除。
ICOMのUSBキーイング対象のみCI-Vハンドル共用可。Kenwood／Yaesuは別COM。外部専用COMは別信号線でFSK/PTTを一つのハンドルで制御できる。
メーカー取扱説明書を実装根拠とし、対応機種は通常機能として案内。実機検証記録は検証資料へ残し、利用者画面へ暫定ラベルを付けない。

MACRO配色 psrtty/macro_colors.py・psrtty/ui/macro_colors_dialog.py。ui.macro_colorsに保存し、Profileとは独立。
言語はja/en/ru/zh/ko/id/th/es、各1313項目。変更後は validate_languages.py --generate と validate_languages.py を実行する。
Windowsでは build-windows.ps1。設定・ログは配布物へ入れず、更新時に既存のconfig・logdata・varを保持する。
サンクスは履歴・CHANGELOG・リリースノートへ記載せず、掲載時期を付けない。ウェブ用は必ず別ZIP。
詳細ルール docs/DEVELOPMENT_RULES.md。
