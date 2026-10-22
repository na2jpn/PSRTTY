# PSRTTY 1.29 — 2026-10-23

報告された1.28の起動停止は、scipy.signalの読込み中に
scipy._external.array_api_compat.numpy.fftが見つからないもの。
ExtIOへの接続・IQ受信より前の依存関係の不足だった。

## 収集対象

build_support/scipy_bundle.pyをpsrtty.specから使用する。
SciPyの_externalおよび_libのarray_api_compatを探し、存在するものの
numpy・common配下をPyInstaller collect_submodules(on_error='raise')で収集する。
fft・linalgが収集されていない場合はビルドエラーにする。
未知の配置へ変更された場合も、黙って不足したEXEを作らずビルドを止める。
Torch、CuPy等のバックエンドやSciPy全体の無差別な収集は追加しない。
既存のPyInstaller標準フックおよびunittestの保持を引き継ぐ。

## 完成したEXEの検査

psrtty.py --self-test-skimmer <JSON出力先> はGUIを作る前に分岐する。
FIR間引きのブロック境界整合を確認し、48kHzの複素IQ信号を2局分合成して
実際のSkimmerEngineへ渡し、JA1ABC・JA2XYZと599 001の復号を確認する。
無線機、ExtIO DLL、Audioデバイスを開かず、CAT/PTTやRF送信を行わない。
importエラーもUTF-8のJSONへ完全なトレースを記録し、非0で終了する。

tools/check_frozen_skimmer.pyは空の一時フォルダーをcwdとして指定EXEを起動。
120秒の期限、終了コード、今回生成されたJSON、ok/frozen属性、版、復号局を確認。
未生成・失敗・旧版・ソース実行ならエラーとし、Windowsビルドを停止する。
build-windows.ps1はPyInstaller後・package_release.py前にこの検査を必須実行する。
従来のソース全件テストも維持する。

この検査は同梱不足とDSPの確認であり、実機のUSB接続・ExtIO DLL固有の動作・
IC-7610の設定やIQデータ到達を保証するものではない。
Windows EXEのサイズ比較と実機受信確認はWindows側で行う。
