# Ver1.26 引継ぎ — 2026-10-17

最新の送信仕様・検証はdocs/USOS_126.md。スペース／改行後のFIGS再送をAFSK一括・AFSKダイレクト・FSKの3経路で維持し、USOS ON/OFF双方で確認すること。送信側の実際のFIGS/LTRS状態は保持し、USOS OFFの受信側で数字の後の英字が化けないようにすること。受信USOSの設定追加は今回の対象外です。

# Ver1.25 正本引継ぎ — 2026-10-17

利用者の動作確認を受けてFIX1適用済みを正本化。最新の受信仕様はdocs/BUFFERED_RX_125.md、検証はdocs/VALIDATION_125_CANONICAL.md。以後はこのフルソースを基準としてください。

# Ver1.25 FIX1 — 2026-10-17

1.25初回の文字間隔1.5秒方式を、復調フレームの連続性方式へ置換。最新仕様はdocs/BUFFERED_RX_125.md。逐次はフレーム終了通知を無視し、従来の生文字表示を維持します。

# Ver1.25 引継ぎ — 2026-10-17

最新の受信仕様はdocs/BUFFERED_RX_125.md。まとめてと逐次の受信文確定を分離し、音声復調は共通のまま維持します。

# Ver1.24 正本引継ぎ — 2026-10-16

最新仕様はdocs/QSO_FREQUENCY_124.md、検証はdocs/VALIDATION_124.md。登録前の周波数確認、取消時に副作用を出さないこと、全外部連携へ共通のQSOを渡すことを維持してください。

# Ver1.23 引継ぎ — 2026-10-16

最新仕様はdocs/INTEGRATION_123.md、検証はdocs/VALIDATION_123.md。Ver1.22は内部配布のみで、公開履歴・リリースノートはVer1.23へ統合しています。Thanksの追加を履歴やリリースノートへ記載しない方針を継続します。

# Ver1.22 引継ぎ — 2026-10-16

このフルソースにVer1.21以前を統合しています。最新仕様はdocs/FSK_PORT_122.md、検証はdocs/VALIDATION_122.mdを参照してください。

# PSRTTY 1.21 フル実装引継ぎ — 2026-10-16

フルソース：PSRTTY_1.21_FULL_SOURCE.zip。派生元は1.20正本。
バージョン：psrtty/__init__.py。仕様 VERSION_121.md、検証 docs/VALIDATION_121.md。

Hamlib set_fsk_mode は送受信状態とモード読取りを0.25秒間隔、各段階最大5回まで再試行する。
確認全体で次の呼出しを開始する期限は2秒。進行中のネイティブI/Oはドライバーのタイムアウトに従う。
モード書込みは最大1回。同じモードなら書込みなし。フィルターを維持し、モード確認後だけPTT。
FSK送信ワーカーのSTOP Eventも渡して待機中断。エラー詳細はfsk_mode_errorとfsk_mode_diagnosticへ記録。
ソフトの利用者表示では対応機種に暫定ラベルを付けない。検証範囲は検証資料に記載。
今後もThanksへの変更を履歴に記載せず、ウェブ用ソースは別ZIPとする。

以下は継承元の構成記録。

# PSRTTY 1.20 正本引継ぎ — 2026-10-16

正本：PSRTTY_1.20_CANONICAL_SOURCE.zip。1.19正本の全機能にFSKメーター修正を統合。
バージョン：psrtty/__init__.py。仕様 VERSION_120.md、検証 docs/VALIDATION_120.md。

FSK時もSWR/PWRをBackgroundJobで取得する。ALCの取得を省き、音量調整の良否判定やAudio設定チェック警告は表示しない。
AudioEngine._fsk_mode_confirmedは送信開始時のモード読返し成功後に設定、送信終了・エラーで解除。
受信中はモードを定期取得し、有効な確認から2秒以内だけFSK表示。切断・世代変更時は確認情報を破棄。
ALCGaugeのFSK表示は枠内の緑文字。通常AFSK時は従来のゲージ表示。
SWR/PWRの表示スイッチと送信終了後2秒保持は共通仕様。

開発方針：1.20を一区切りにし、不具合がなければIC-7710発売まで更新を休止する可能性あり。
今後もThanksへの追加を更新履歴・リリースノート・日付付き記録に書かない。ウェブ用ソースは別ZIP。

以下は継承元の構成記録。

# PSRTTY 1.19 正本引継ぎ — 2026-10-15

正本：PSRTTY_1.19_CANONICAL_SOURCE.zip。1.18正本にフィルター保持修正を統合。
バージョン：psrtty/__init__.py。仕様 VERSION_119.md、検証 docs/VALIDATION_119.md。
ICOM set_fsk_mode は送信前にモードを読み、同じモードでは書き換えない。
切替が必要な場合もCI-V 06コマンドのフィルター指定を省略し、読返しを確認する。
FIL1の固定指定を戻さないこと。
Hamlib set_fsk_mode も先に読み、同じモードなら再設定を省く。切替時は既存の帯域幅変更なし指定（-1）を維持し、モードを読返す。

以下は継承元1.18の構成記録。

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
