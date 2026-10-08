import unittest
from copy import deepcopy
from unittest.mock import Mock, patch
from pathlib import Path
from psrtty.secondary_audio import secondary_choices
from psrtty.ui.secondary_audio_dialog import SecondaryAudioDialog
from psrtty.ui.settings_dialog import SettingsDialog
from psrtty.i18n import configure, tr
from tests import test_ui_v02 as fixture


def device(identifier,name):
    return {'backend':'wasapi','id':identifier,'kind':'output','name':name}

class ChoicesTests(unittest.TestCase):
    def test_explicit_and_auto_exclude_identity_not_name(self):
        a,b=device('a','USB'),device('b','USB')
        rows=[dict(index=1,choice=a,label='USB A'),dict(index=2,choice=b,label='USB B')]
        for primary in (a,dict(a,name='old name'),'AUTO'):
            with patch('psrtty.audio_devices.enumerate_devices',return_value=rows),patch('psrtty.secondary_audio.resolve_device',return_value=1):
                choices,excluded=secondary_choices(primary)
            self.assertEqual(choices,[(b,'USB B')]);self.assertIn(a,excluded)
        with patch('psrtty.audio_devices.enumerate_devices',return_value=rows),patch('psrtty.secondary_audio.resolve_device',side_effect=ValueError('disconnected')):
            choices,_=secondary_choices(a);self.assertEqual(choices,[(b,'USB B')])
            with self.assertRaises(ValueError):secondary_choices('AUTO')

    def test_history_only_108_date_changes(self):
        from psrtty.update_history import HISTORY_TEXT
        from psrtty.update_history_en import HISTORY_TEXT_EN
        for text in (HISTORY_TEXT,HISTORY_TEXT_EN):
            section=next(block for block in text.split('\n\n') if 'Ver1.08' in block.splitlines()[0])
            self.assertIn('2026-10-04',section.splitlines()[0])
            previous=next(block for block in text.split('\n\n') if 'Ver1.07' in block.splitlines()[0])
            self.assertIn('2026-10-03',previous.splitlines()[0])
            self.assertNotIn('FIX1',text.split('\n\n',1)[0])

class UI108Fix1Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp;tearDown=fixture.UITests.tearDown;pump=fixture.UITests.pump

    def test_cancel_and_failed_save_never_open(self):
        d=SettingsDialog(self.store,self.window)
        with patch.object(d,'_confirm_primary_audio_save',return_value=False),patch('psrtty.ui.secondary_audio_dialog.SecondaryAudioDialog') as dialog:
            d._open_secondary_audio();dialog.assert_not_called();self.store.save.assert_not_called()
        old=deepcopy(self.store.data);d.tx_gain.setValue(42);self.store.save.side_effect=OSError('disk full')
        with patch.object(d,'_confirm_primary_audio_save',return_value=True),patch('psrtty.ui.secondary_audio_dialog.SecondaryAudioDialog') as dialog,patch('psrtty.ui.settings_dialog.QMessageBox.warning') as warning:
            d._open_secondary_audio();dialog.assert_not_called();warning.assert_called_once()
        self.assertEqual(self.store.data,old);self.store.save.side_effect=None;d.reject()

    def test_save_precedes_open_and_commits_only_primary_output(self):
        d=SettingsDialog(self.store,self.window);a=device('a','Main')
        d.audio_out.addItem('Main',a);d.audio_out.setCurrentIndex(d.audio_out.count()-1);d.tx_gain.setValue(42)
        old_in=self.store.data['audio']['input_device'];old_secondary=deepcopy(self.store.data['audio']['secondary'])
        def created(*args,**kwargs):
            self.store.save.assert_called_once()
            self.assertEqual(self.store.data['audio']['output_device'],a)
            self.assertEqual(self.store.data['audio']['tx_gain'],.42)
            self.assertEqual(kwargs['primary_device'],a)
            return Mock()
        with patch.object(d,'_confirm_primary_audio_save',return_value=True),patch('psrtty.ui.secondary_audio_dialog.SecondaryAudioDialog',side_effect=created):d._open_secondary_audio()
        d.reject()
        self.assertEqual(self.store.data['audio']['input_device'],old_in)
        self.assertEqual(self.store.data['audio']['secondary'],old_secondary)
        self.assertEqual(self.window.audio.tx_gain,.42)

    def test_inactive_profile_save_does_not_change_active(self):
        second=deepcopy(self.store.data['profiles'][0]);second['name']='P2';self.store.data['profiles'].append(second)
        d=SettingsDialog(self.store,self.window);d.profile_tabs.setCurrentIndex(1)
        active=deepcopy(self.store.data['audio']);d.tx_gain.setValue(55)
        d._save_primary_before_secondary()
        self.assertEqual(self.store.data['audio'],active)
        self.assertEqual(self.store.data['profiles'][1]['audio']['tx_gain'],.55)
        d.reject()

    def test_excluded_saved_secondary_not_reinserted_bilingual(self):
        a,b=device('a','USB'),device('b','USB')
        for language in ('ja','en'):
            configure(language)
            with patch('psrtty.ui.secondary_audio_dialog.secondary_choices',return_value=([(b,'USB B')],[a])):
                d=SecondaryAudioDialog({'enabled':True,'device':dict(a,name='old'),'gain':1},Mock(),self.window,primary_device=a)
            self.assertEqual(d.device.count(),2);self.assertEqual(d.device.currentData(),'UNSET')
            self.assertEqual(d.device.itemData(1),b);d.save();self.assertEqual(d.status.text(),tr('第二AudioOUTの出力先を選択してください。'))
            d.close()
        configure('ja')
