# PSRTTY Ver1.07 — 2026-10-03

2026-10-03　Ver1.07
・「表示」と「Language」の間に「連携」メニューを追加しました。HAMLOG連携設定とzLog令和版連携設定を開けます。
・Turbo HAMLOG/Win Ver5.48を対象に、PSRTTYの記録後に交信を転送する機能を追加しました。手動記録・TU73自動記録で共通です。入力欄への転送のみ、または転送後の保存指示を選べます。
・HAMLOGの接続確認とCALL検索・氏名／QTH取得を追加しました。転送失敗時は元のADIFを維持し、理由と対処方法を表示します。入力中の交信の保護と、結果不明時の自動再送防止に対応しました。
・zLog 3.0.4.0向けに、一般・JARL WW RTTY・CQ WW RTTYのADIF出力を追加しました。元の交換番号を備考にも保持します。CQ WW RTTYの州・地域は、取り込み後に受信番号とマルチの確認・修正が必要です。
・初期設定ガイドに「HAMLOGなど連携」タブを追加し、対応対象バージョンと操作方法を日英で記載しました。
・対応表のYaesu・Kenwood全機種へHamlib経由のNB・NRの取得・変更を広げました。YaesuはDNRと表示し、変更後の状態を確認します。
・FT-710、FTDX10、FTDX101D／MP、FTDX3000の受信フィルター幅に対応し、FT-991／FT-991A・FTX-1の選択肢を機種別の仕様に合わせました。TS-590SGのDATA／SSBは低域カットを維持して受信幅を変更します。TS-890S・TS-990Sの受信幅はHamlib 4.7.2未実装のため本体操作となります。
・スペシャルサンクスをスクロール可能にし、JQ7FIUとMMTTY・Turbo HAMLOG・zLogなどの開発者への謝辞を追加しました。

2026-10-03  Ver1.07
・Added Integration between View and Language, with HAMLOG and zLog Reiwa integration settings.
・Added QSO transfer to Turbo HAMLOG/Win Ver5.48 after successful PSRTTY logging, for both manual and TU73 auto logging. Choose input-only transfer or a save request after transfer.
・Added HAMLOG connection checking and CALL / Name / QTH lookup. Transfer errors retain the local ADIF record and show recovery guidance. Existing drafts are protected; uncertain transfers are not retried automatically.
・Added General zLog, JARL WW RTTY and CQ WW RTTY ADIF exports targeting zLog 3.0.4.0. Original exchanges are also retained in notes. CQ WW RTTY state/province exchanges and multipliers require checking and correction after import.
・Added a bilingual HAMLOG / integrations setup-guide tab, including target versions and operating instructions.
・Extended Hamlib NB/NR read/write to all listed Yaesu and Kenwood models, with state readback. Yaesu uses the DNR label.
・Added receive width control for FT-710, FTDX10, FTDX101D/MP and FTDX3000; corrected FT-991/FT-991A and FTX-1 choices to model-specific tables. TS-590SG DATA/SSB width adjustment preserves low cut. TS-890S/TS-990S bandwidth is not implemented in Hamlib 4.7.2 and must be controlled on the radio.
・Made Special Thanks scrollable and added JQ7FIU and thanks to the developers of MMTTY, Turbo HAMLOG, zLog and related software.

RTTYプリンターの処理と設定は1.06正本から変更していません。
全ソース版です。Windows EXEは同梱しません。Windowsで build-windows.ps1 を実行してください。
設定・Profile・マクロ・ログは既存のものを維持します。HAMLOG連携は初期OFFです。

詳細は docs/INTEGRATION_107_JA.html、docs/INTEGRATION_107_EN.html、docs/INTEGRATION_SOURCE_REVIEW_107.md を参照してください。
