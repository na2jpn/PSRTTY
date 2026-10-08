# PSRTTY Ver1.08 — 2026-10-04

2026-10-04　Ver1.08
・IC-7760を無線機の選択肢に追加しました。CI-V初期アドレスはB2です。周波数、LSB-D／USB-D（DATA1）、PTT、FIL1～3、NB／NR／NOTCH、ALC、アンテナTUNEに対応し、DATA2／3時もフィルターの取得・変更に対応します。DATA1の変調入力をUSBに設定してください。
・Audio OUT設定に「第二AudioOUTの設定」を追加しました。開く前に主AudioOUTの出力先と音量を確認して保存し、保存した主出力先（自動選択を含む）は第二出力の候補から除外します。主出力と同じ送信音を別の機器に出力でき、プロファイルごとに有効／無効、出力先、独立した音量を保存します。初期状態は無効です。「未接続でも送信可」がONで第二AudioOUTが有効な場合は、両方の出力先を個別に確認し、片方でも使えれば音声を出力します。両方が使えない場合は理由を案内します。
・第二AudioOUTの音量は0～200％（初期100％）で、100％を超えるとゲージが赤くなります。専用画面には「保存」「閉じる」を配置し、PTT操作・テストは設けていません。第二出力の不具合は状態欄で案内し、主送信を継続します。
・「～について」のボタン名を「サンクス」に変更しました。スペシャルサンクスにJH1PGF、メディアサンクスにhamlife.jpを追加し、スクロール表示と従来の感謝文を維持しました。
・画面用PNGの読み込みエラーでアイコンが表示されない問題を修正しました。Windowsのアプリ識別設定を追加し、複数サイズのアイコンを実行時にも同梱・使用するよう改善しました。
・新しい設定・案内・ガイド・更新履歴の英語表示に対応しました。

2026-10-04  Ver1.08
・Added IC-7760 with default CI-V address B2. Supports frequency, LSB-D/USB-D (DATA1), PTT, FIL1–3, NB/NR/NOTCH, ALC and antenna TUNE. Filter read/write also preserves DATA2/3. Set DATA1 modulation input to USB on the radio.
・Added Secondary Audio OUT settings. Before opening, confirm and save the primary output device and volume. Its device, including an automatically selected default, is excluded from the secondary list. Send the same TX waveform to a separate output with independently saved device, enable switch and volume per profile. Disabled by default. With disconnected TX allowed and secondary Audio OUT enabled, each output is tried independently; playback proceeds if either works. If neither is usable, the reason is shown.
・Secondary volume ranges from 0–200% (default 100%); the slider turns red above 100%. The dedicated window provides Save and Close without PTT or test controls. Secondary-output errors appear in the status area while primary transmission continues.
・Renamed the About button to Thanks. Added JH1PGF to Special Thanks and hamlife.jp under Media Thanks, preserving scrolling and existing acknowledgments.
・Fixed missing icons caused by an unreadable runtime PNG. Added explicit Windows application identity and bundled a multi-size icon for runtime use to improve taskbar icon handling.
・Added English labels, guidance, setup instructions and release history for these changes.
