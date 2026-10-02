# PSRTTY Ver1.06 FIX1

Windowsでtest_export_menu_order_and_exclusive_checksが「Internal C++ object (PySide6.QtWidgets.QMenu) already deleted」で失敗するケースに対応しました。版番号は1.06のままです。

MainWindowがトップレベルのQMenuをPython側でも保持します。ファイルメニューもself.file_menuで参照を保持します。テストはmenuBar().actions()[0].menu().actions()という一時オブジェクトの連続取得をやめ、メニューバー、アクション一覧、先頭アクション、メニューを個別に保持して取得します。GC後にもメニューが有効であることを検証し、メニュー順・単一チェックの検証は維持します。

既存のファイル出力・表示設定・言語・無線機操作の内容は変えていません。Windowsでの元の失敗はユーザー提供の結果です。修正後のWindows実機試験は未実施です。
