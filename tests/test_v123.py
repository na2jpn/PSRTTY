"""HAMLOG CALL/Enter ordering, exact diagnostics and Hamlib debug policy."""
import copy
import ctypes
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from psrtty import i18n
from psrtty.hamlog_csv import hamlog_row
from psrtty.hamlog_link import HamlogLink,LinkError,THW_ENTER,THW_SAVEBOX_OFF,transfer_mismatches
from psrtty.hamlib_radio import HamlibController,HAMLIB_MODELS,load_library
from tests.test_v107 import FakeHamlog,qso


class EnterHamlog(FakeHamlog):
    """Require Enter to enable Save; simulate lookup changing QSO fields."""
    def __init__(self):
        super().__init__();self.entered=False;self.values_ready=False
        self.alter={};self.enter_call=None
    def request(self,command,text=None,reply=False):
        if command==(18|THW_SAVEBOX_OFF) and not self.entered:
            raise AssertionError('Save before CALL Enter')
        result=super().request(command,text,reply)
        if command in (4,5) and self.fields[6]!='RTTY':
            self.fields[command-1]=text[:2]
        if command==(1|THW_ENTER):
            self.entered=True
            self.fields[1:7]=['00/01/01','00:00J','59','59','7.000','SSB']
            self.fields[7:12]=['1234','PM95','J','Lookup name','Lookup QTH']
            self.fields[12:14]=['lookup remarks','lookup station']
            if self.enter_call is not None:self.fields[0]=self.enter_call
        if command==14:self.values_ready=True
        if command==115 and self.values_ready:
            fields=list(self.fields)
            for index,value in self.alter.items():fields[index]=value
            result='\r\n'+'\r\n'.join(fields)+'\r\n'
        return result


class Hamlog123Tests(unittest.TestCase):
    def setUp(self):
        i18n.configure('ja');self.addCleanup(i18n.configure,'ja')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.api=EnterHamlog();self.link=HamlogLink(Path(self.tmp.name)/'journal.jsonl',lambda:self.api)

    def test_enter_precedes_qso_fields_verify_and_single_save(self):
        record=qso();self.link.transfer(record,True)
        commands=[c[0] for c in self.api.commands]
        self.assertEqual(commands,[115,1|THW_ENTER,115,7,2,3,4,5,6,13,14,115,18|THW_SAVEBOX_OFF,101])
        saved=self.api.saved[0];row=hamlog_row(record)
        for index in (0,1,2,3,4,5,6,12,13):self.assertEqual(saved[index],row[index])
        self.assertEqual(saved[7:12],['1234','PM95','J','Lookup name','Lookup QTH'])

    def test_input_only_still_enters_call_but_never_saves(self):
        self.link.transfer(qso(),False)
        self.assertTrue(self.api.entered);self.assertFalse(self.api.saved)
        self.assertNotIn(18|THW_SAVEBOX_OFF,[c[0] for c in self.api.commands])
        self.assertEqual(self.api.fields[:7],hamlog_row(qso())[:7])

    def test_enter_timeout_stops_before_qso_fields_or_save_and_is_not_retried(self):
        self.api.fail_on=1|THW_ENTER
        with self.assertRaises(LinkError):self.link.transfer(qso(),True)
        self.assertEqual([c[0] for c in self.api.commands],[115,1|THW_ENTER])
        self.api.fail_on=None;before=list(self.api.commands)
        with self.assertRaises(LinkError):self.link.transfer(qso(),True)
        self.assertEqual(self.api.commands,before)
        self.assertFalse(self.api.saved)

    def test_wrong_call_after_enter_never_writes_remaining_fields(self):
        self.api.enter_call='JA9XYZ'
        with self.assertRaises(LinkError) as error:self.link.transfer(qso(),True)
        self.assertIn('CALL',str(error.exception));self.assertIn('JA9XYZ',str(error.exception))
        self.assertIn('JA1ABC',str(error.exception));self.assertFalse(self.api.saved)
        self.assertEqual([c[0] for c in self.api.commands],[115,1|THW_ENTER,115])

    def test_each_mismatch_reports_both_values_and_prevents_save(self):
        cases={0:('CALL','JA9XYZ'),1:('DATE','26/10/04'),2:('TIME','00:00J'),
            3:('RST-S','59'),4:('RST-R','59'),5:('FREQ','50.3030'),6:('MODE','SSB'),
            12:('Remarks1','changed'),13:('Remarks2','')}
        row=hamlog_row(qso())
        for index,(name,value) in cases.items():
            with self.subTest(field=name),tempfile.TemporaryDirectory() as td:
                api=EnterHamlog();api.alter={index:value};link=HamlogLink(Path(td)/'j',lambda:api)
                with self.assertRaises(LinkError) as error:link.transfer(qso(),True)
                message=str(error.exception)
                self.assertIn(name,message);self.assertIn(json.dumps(value,ensure_ascii=False),message)
                self.assertIn(json.dumps(row[index],ensure_ascii=False),message)
                self.assertFalse(api.saved)
                if index in (3,4):self.assertIn('599',message)

    def test_multiple_mismatches_are_reported_without_falsely_marking_other_fields(self):
        self.api.alter={2:'bad time',3:'59',4:'59'}
        with self.assertRaises(LinkError) as error:self.link.transfer(qso(),True)
        message=str(error.exception)
        self.assertIn('TIME：',message);self.assertIn('RST-S：',message);self.assertIn('RST-R：',message)
        self.assertNotIn('DATE：',message);self.assertNotIn('FREQ：',message)

    def test_equivalent_date_and_frequency_formats_still_match(self):
        self.api.alter={1:'2026/10/03',5:'14.085000',6:'rtty'}
        self.link.transfer(qso(),True);self.assertEqual(len(self.api.saved),1)

    def test_invalid_frequency_does_not_hide_the_other_mismatches(self):
        row=hamlog_row(qso());actual=list(row[:14]);actual[5]='NaN';actual[13]='wrong'
        self.assertEqual([x[0] for x in transfer_mismatches(row,actual)],['FREQ','Remarks2'])
        actual[5]='not a frequency'
        self.assertEqual([x[0] for x in transfer_mismatches(row,actual)],['FREQ','Remarks2'])

    def test_rsts_are_not_coerced_and_timezone_marker_is_required(self):
        row=hamlog_row(qso());actual=list(row[:14]);actual[3]='59';actual[2]=row[2][:-1]
        self.assertEqual([x[0] for x in transfer_mismatches(row,actual)],['TIME','RST-S'])

    def test_owned_lookup_gets_enter_before_final_qso_and_foreign_draft_is_protected(self):
        self.link.lookup(qso().call);self.link.transfer(qso(),True)
        self.assertEqual(len(self.api.saved),1)
        self.assertEqual(sum(c[0]==(1|THW_ENTER) for c in self.api.commands),2)
        api=EnterHamlog();api.fields[0]='JA9XYZ';link=HamlogLink(Path(self.tmp.name)/'other',lambda:api)
        with self.assertRaises(LinkError):link.transfer(qso(),True)
        self.assertFalse(api.entered);self.assertEqual([c[0] for c in api.commands],[115])

    def test_guides_diagnostics_and_public_history_in_all_eight_languages(self):
        root=Path(__file__).resolve().parents[1]
        for lang in i18n.LANGUAGES:
            i18n.configure(lang)
            self.assertIn('599',i18n.tr('v123.rtty_setup'))
            self.assertIn(i18n.tr('v123.rtty_setup'),i18n.tr('guide.8.body'))
            self.assertIn('Enter',i18n.tr('guide.8.body'));self.assertIn('Save',i18n.tr('guide.8.body'))
            item=i18n.tr('v123.mismatch_item').format(field='FREQ',sent='"14.085"',received='"50.303"')
            self.assertIn('14.085',item);self.assertNotIn('v123.',item)
            history=i18n.tr('history.body');self.assertTrue(history.startswith('2026-10-23  Ver1.29\n'))
            self.assertNotIn('Ver1.22',history);self.assertIn('Ver1.21',history)
        for name in ('CHANGELOG.md','UPDATE_HISTORY.txt'):
            self.assertNotIn('Ver1.22',(root/name).read_text(encoding='utf-8'))


class Debug123Tests(unittest.TestCase):
    def test_debug_signature_has_void_return_and_int_argument(self):
        library=Mock()
        with patch('psrtty.hamlib_radio.sys.platform','freebsd13'),patch('psrtty.hamlib_radio.ctypes.util.find_library',return_value='libhamlib.so'),patch('psrtty.hamlib_radio.ctypes.CDLL',return_value=library):
            lib,_=load_library()
        self.assertIsNone(lib.rig_set_debug.restype)
        self.assertEqual(lib.rig_set_debug.argtypes,[ctypes.c_int])

    def test_debug_disabled_before_init_for_every_hamlib_model(self):
        for model in HAMLIB_MODELS:
            with self.subTest(model=model):
                library=Mock();library.rig_init.return_value=1;library.rig_open.return_value=0
                ctl=HamlibController(model)
                with patch('psrtty.hamlib_radio.load_library',return_value=(library,None)),patch.object(ctl,'_configure'),patch.object(ctl,'read_frequency',return_value=14085000):
                    self.assertTrue(ctl.connect('COM3',38400).connected)
                    self.assertEqual(library.method_calls[:2],[('rig_set_debug',(0,),{}),('rig_init',(HAMLIB_MODELS[model][0],),{})])
                    ctl.disconnect()


if __name__=='__main__':unittest.main()
