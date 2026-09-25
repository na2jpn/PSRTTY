import json
import unittest
from PySide6.QtWidgets import QMenu
from pathlib import Path
from unittest.mock import patch
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.config import ConfigStore

class UI40Tests(unittest.TestCase):
    setUpClass = classmethod(_Fixture.setUpClass.__func__)
    setUp = _Fixture.setUp
    tearDown = _Fixture.tearDown
    pump = _Fixture.pump
    def test_connection_toggle_and_connecting_guard(self):
        w=self.window
        with patch.object(w,'_connected',return_value=False), patch.object(w,'connect_radio') as connect:
            w.rig_status.click();connect.assert_called_once()
            w.connecting=True;w._set_radio_controls()
            self.assertEqual(w.rig_status.text(),'接続中…');self.assertFalse(w.rig_status.isEnabled())
            w._toggle_connection();self.assertEqual(connect.call_count,1)
        w.connecting=False
        with patch.object(w,'_connected',return_value=True),patch.object(w,'disconnect_radio') as disconnect:
            w._set_radio_controls();self.assertEqual(w.rig_status.text(),'接続')
            w.rig_status.click();disconnect.assert_called_once()

    def test_latest_counts_gap_and_log_link(self):
        w=self.window;w.latest_panel.resize(1200,100)
        for count in (2,4,6,8,10):
            w._set_latest_count(count)
            self.assertFalse(w.latest_right.isHidden())
            self.assertEqual(w.latest_table.height(),w.latest_table.horizontalHeader().sizeHint().height()+count//2*24+4)
        self.assertEqual(w.latest_panel.layout().spacing(),14)
        with patch.object(w,'_show_qso_log') as show:
            w.latest_table.doubleClicked.emit(w.latest_table.model().index(0,0))
            w.latest_right.doubleClicked.emit(w.latest_right.model().index(0,0))
            self.assertEqual(show.call_count,2)
        menu_bar=w.menuBar()
        menus=menu_bar.findChildren(QMenu)
        labels=[a.text() for m in menus for a in m.actions()]
        self.assertIn('QSOログ',labels);self.assertNotIn('QSOログ一覧',labels)
        self.assertNotIn('RTTYチューニングについて',labels)

    def test_config_migration_once_preserves_macros(self):
        root=Path(self.tmp.name);cfg=root/'settings.json';mac=root/'macros.json'
        cfg.write_text(json.dumps({'ui':{'latest_qso_count':5,'rx_card_font_size':14}}))
        with patch('psrtty.config.ensure_runtime_dirs',return_value=self.paths):
            store=ConfigStore(cfg,mac)
            self.assertEqual(store.data['ui']['latest_qso_count'],4)
            self.assertEqual(store.data['ui']['rx_card_font_size'],12)
            store.save();again=ConfigStore(cfg,mac)
            self.assertEqual(again.data['ui']['rx_card_font_size'],12)
            self.assertEqual(again.macros,store.macros)
            cfg.unlink();fresh=ConfigStore(cfg,mac)
            self.assertEqual(fresh.data['ui']['rx_card_font_size'],12)

del _Fixture
