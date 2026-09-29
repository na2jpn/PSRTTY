import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
from PySide6.QtWidgets import QApplication, QMessageBox
from psrtty.config import ConfigStore, DEFAULT_CONFIG, profile_name
from psrtty.ui.settings_dialog import SettingsDialog
from psrtty.ui.main_window import MainWindow
from psrtty.ui.sub_decode import SubDecodeWindow
from psrtty.ui.guide import PAGES


class Profile105Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_legacy_config_is_profile_one_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'psrtty.json'
            config.write_text(json.dumps({'version':'1.01', 'station_callsign':'JH1HST',
                'radio':{'model':'IC-705'}, 'audio':{'input_device':'UNSET'},
                'station':{'qth':'SOKA'}}), encoding='utf-8')
            with patch('psrtty.config.ensure_runtime_dirs', return_value={'config':root}):
                store = ConfigStore(config, root / 'macros.json')
            self.assertEqual(store.data['profiles'][0]['name'], 'Profile1')
            self.assertEqual(store.data['profiles'][0]['radio']['model'], 'IC-705')
            self.assertEqual(store.data['profiles'][0]['station']['qth'], 'SOKA')
            store.data['ui']['rx_tones'] = [2100, 2270]
            store.snapshot_profile()
            store.data['profiles'].append({**deepcopy(store.data['profiles'][0]), 'name':'Rig2'})
            store.activate_profile(1)
            self.assertEqual(store.data['ui']['rx_tones'], [2100, 2270])
            store.data['radio']['model'] = 'IC-7300'
            store.data['ui']['rx_tones'] = [2150, 2320]
            store.save()
            store.activate_profile(0)
            self.assertEqual(store.data['radio']['model'], 'IC-705')
            self.assertEqual(store.data['ui']['rx_tones'], [2100, 2270])
            with patch('psrtty.config.ensure_runtime_dirs', return_value={'config':root}):
                reloaded = ConfigStore(config, root / 'macros.json')
            self.assertEqual(reloaded.data['profiles'][1]['radio']['model'], 'IC-7300')
            self.assertEqual(reloaded.data['active_profile'], 0)

    def test_settings_two_levels_rename_and_add(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('psrtty.config.ensure_runtime_dirs', return_value={'config':root}), \
                 patch('psrtty.ui.settings_dialog.AudioEngine.devices', return_value=[]), \
                 patch('psrtty.ui.settings_dialog.CIVController.port_choices', return_value=[]):
                store = ConfigStore(root/'psrtty.json', root/'macros.json')
                dialog = SettingsDialog(store)
                self.assertEqual(dialog.profile_tabs.tabText(0), 'Profile1')
                self.assertEqual(dialog.tabs.tabText(0), '基本設定')
                dialog.profile_name_edit.setText('IC705')
                dialog.my_qth.setText('SOKA')
                dialog._add_profile()
                self.assertEqual(dialog.profile_tabs.tabText(0), 'IC705')
                self.assertEqual(dialog.profile_tabs.count(), 2)
                dialog.profile_name_edit.setText('IC7300')
                dialog.my_qth.setText('TOKYO')
                dialog._save()
                self.assertEqual([p['name'] for p in store.data['profiles']], ['IC705','IC7300'])
                self.assertEqual([p['station']['qth'] for p in store.data['profiles']], ['SOKA','TOKYO'])
                self.assertEqual(store.data['active_profile'], 0)
                dialog.close()

    def test_disconnected_radio_does_not_block_profile_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {'root':root, **{key:root/key for key in ('config','var','logdata')}}
            for path in paths.values(): path.mkdir(exist_ok=True)
            with patch('psrtty.config.ensure_runtime_dirs', return_value=paths):
                store = ConfigStore(root/'config/psrtty.json', root/'config/macros.json')
            second = deepcopy(store.data['profiles'][0])
            second['name'] = 'Rig2'
            second['radio']['model'] = 'IC-705'
            second['radio']['com_port'] = 'COM11'
            store.data['profiles'].append(second)
            with patch('psrtty.ui.main_window.ensure_runtime_dirs', return_value=paths), \
                 patch('psrtty.ui.main_window.ConfigStore', return_value=store), \
                 patch('psrtty.ui.main_window.TranscriptLogger'), \
                 patch('psrtty.ui.main_window.ADIFLog'):
                window = MainWindow()
                try:
                    with patch.object(window, 'connect_radio') as connect:
                        window._switch_profile(1)
                    self.assertEqual(store.data['active_profile'], 1)
                    self.assertEqual(window.profile_buttons.itemAt(1).widget().text(), 'Rig2')
                    connect.assert_not_called()
                    window._profile_switch = True
                    window._profile_connect_failed('COM11を開けません')
                    self.assertEqual(store.data['active_profile'], 1)
                    self.assertIn('COM11を開けません', window.statusBar().currentMessage())
                    sub = SubDecodeWindow(window)
                    sub._line_clicked('CQ DE JA1ABC JA1ABC')
                    self.assertEqual(window.q_call.text(), 'JA1ABC')
                    sub._line_clicked('NO CALL HERE')
                    self.assertEqual(window.q_call.text(), 'JA1ABC')
                    for message in ('CQ DE JA1ABC', 'CQ DE JH1XYZ'):
                        sub.buffers[0] = message
                        sub._flush(0)
                    first = sub.outputs[0].document().firstBlock()
                    second = first.next()
                    self.assertNotEqual(first.blockFormat().background().color(),
                                        second.blockFormat().background().color())
                    for message in ('CQ DE JA1ABC', 'CQ DE JH1XYZ'):
                        sub.buffers[1] = message
                        sub._flush(1)
                    blue = sub.outputs[1].document().firstBlock().next()
                    self.assertNotEqual(second.blockFormat().background().color(),
                                        blue.blockFormat().background().color())
                    self.assertEqual(window.profile_buttons.itemAtPosition(0, 0).widget().height(), 22)
                    sub.close()
                finally:
                    store.data['backup']['on_exit'] = False
                    window.close()

    def test_delete_profile_keeps_active_selection_and_cancel_is_reversible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('psrtty.config.ensure_runtime_dirs', return_value={'config':root}), \
                 patch('psrtty.ui.settings_dialog.AudioEngine.devices', return_value=[]), \
                 patch('psrtty.ui.settings_dialog.CIVController.port_choices', return_value=[]):
                store = ConfigStore(root/'psrtty.json', root/'macros.json')
                for name in ('Profile2', 'Profile3'):
                    store.data['profiles'].append({**deepcopy(store.data['profiles'][0]), 'name':name})
                store.activate_profile(2)
                dialog = SettingsDialog(store)
                dialog.profile_tabs.setCurrentIndex(1)
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                    dialog._delete_profile()
                self.assertEqual(dialog.profile_tabs.currentIndex(), 0)
                self.assertEqual(dialog.active_profile_index, 1)
                self.assertEqual(store.data['active_profile'], 2)
                dialog.reject()
                self.assertEqual(len(store.data['profiles']), 3)
                again = SettingsDialog(store)
                again.profile_tabs.setCurrentIndex(1)
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                    again._delete_profile()
                again._save()
                self.assertEqual([p['name'] for p in store.data['profiles']], ['Profile1', 'Profile3'])
                self.assertEqual(store.data['active_profile'], 1)
                with patch('psrtty.config.ensure_runtime_dirs', return_value={'config':root}):
                    loaded = ConfigStore(root/'psrtty.json', root/'macros.json')
                self.assertEqual(loaded.data['profiles'][1]['name'], 'Profile3')

    def test_six_profile_add_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('psrtty.config.ensure_runtime_dirs', return_value={'config':root}), \
                 patch('psrtty.ui.settings_dialog.AudioEngine.devices', return_value=[]), \
                 patch('psrtty.ui.settings_dialog.CIVController.port_choices', return_value=[]):
                store = ConfigStore(root/'psrtty.json', root/'macros.json')
                dialog = SettingsDialog(store)
                for _ in range(5): dialog._add_profile()
                self.assertEqual(dialog.profile_tabs.count(), 6)
                with patch.object(QMessageBox, 'information') as message:
                    dialog._add_profile()
                message.assert_called_once()
                self.assertEqual(dialog.profile_tabs.count(), 6)
                dialog.reject()

    def test_settings_opens_profile_one_even_when_another_is_active(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('psrtty.config.ensure_runtime_dirs', return_value={'config':root}), \
                 patch('psrtty.ui.settings_dialog.AudioEngine.devices', return_value=[]), \
                 patch('psrtty.ui.settings_dialog.CIVController.port_choices', return_value=[]):
                store = ConfigStore(root/'psrtty.json', root/'macros.json')
                store.data['profiles'][0]['station']['qth'] = 'SOKA'
                store.data['station']['qth'] = 'SOKA'
                other = deepcopy(store.data['profiles'][0])
                other['name'] = 'FTX-1/USB'
                other['station']['qth'] = 'TOKYO'
                store.data['profiles'].append(other)
                store.activate_profile(1)
                dialog = SettingsDialog(store)
                self.assertEqual(dialog.profile_tabs.currentIndex(), 0)
                self.assertEqual(dialog.profile_index, 0)
                self.assertEqual(dialog.my_qth.text(), 'SOKA')
                self.assertEqual(dialog.tabs.currentIndex(), 0)
                dialog.profile_tabs.setCurrentIndex(1)
                self.assertEqual(dialog.my_qth.text(), 'TOKYO')
                dialog.reject()
        self.assertEqual(profile_name('FTX-1/USB'), 'FTX-1/USB')
        self.assertEqual(profile_name('BAD_NAME'), '')
        guide = PAGES[0][1]
        self.assertLess(guide.index('<li><b>無線機 →'), guide.index('<h3>Profileの設定</h3>'))
        self.assertLess(guide.index('<h3>Profileの設定</h3>'), guide.index('<h3>コンテストでAuto CQ'))

if __name__ == '__main__': unittest.main()
