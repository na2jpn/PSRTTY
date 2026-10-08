import unittest
from unittest.mock import patch

from psrtty.hamlib_radio import HamlibController, HAMLIB_MODELS, load_library


class FakeLibrary:
    def __init__(self):self.events=[];self.frequency=14_085_000;self.ptt=0;self.mode=0
    def rig_init(self,model):self.events.append(('model',model));return 123
    def rig_cleanup(self,handle):self.events.append(('cleanup',handle));return 0
    def rig_open(self,handle):self.events.append(('open',handle));return 0
    def rig_close(self,handle):self.events.append(('close',handle));return 0
    def rig_token_lookup(self,handle,name):return {b'rig_pathname':1,b'serial_speed':2}[name]
    def rig_set_conf(self,handle,token,value):self.events.append(('conf',token,value));return 0
    def rig_get_freq(self,handle,vfo,out):out._obj.value=self.frequency;return 0
    def rig_set_freq(self,handle,vfo,hz):self.frequency=int(hz);return 0
    def rig_get_ptt(self,handle,vfo,out):out._obj.value=self.ptt;return 0
    def rig_set_ptt(self,handle,vfo,on):self.events.append(('ptt',on));self.ptt=on;return 0
    def rig_parse_mode(self,name):return {b'PKTLSB':1024,b'PKTUSB':2048}[name]
    def rig_set_mode(self,handle,vfo,mode,width):self.mode=mode;return 0
    def rig_get_mode(self,handle,vfo,mode,width):mode._obj.value=self.mode;return 0


class HamlibBridgeTest(unittest.TestCase):
    def test_library_search_prefers_shared_library_on_non_windows(self):
        class FakeFunction:
            def __call__(self, *args, **kwargs):
                return 0

        class FakeLibrary:
            def __init__(self):
                self.rig_init = FakeFunction()
                self.rig_cleanup = FakeFunction()
                self.rig_open = FakeFunction()
                self.rig_close = FakeFunction()
                self.rig_token_lookup = FakeFunction()
                self.rig_set_conf = FakeFunction()
                self.rig_get_freq = FakeFunction()
                self.rig_set_freq = FakeFunction()
                self.rig_get_ptt = FakeFunction()
                self.rig_set_ptt = FakeFunction()
                self.rig_parse_mode = FakeFunction()
                self.rig_get_mode = FakeFunction()
                self.rig_set_mode = FakeFunction()

        with patch('psrtty.hamlib_radio.sys.platform', 'freebsd13'), \
             patch('psrtty.hamlib_radio.ctypes.util.find_library', return_value='libhamlib-4.so.4'), \
             patch('psrtty.hamlib_radio.ctypes.CDLL', return_value=FakeLibrary()) as cdll:
            lib, directory = load_library()
        self.assertIsNone(directory)
        self.assertEqual(cdll.call_args[0][0], 'libhamlib-4.so.4')
        self.assertIsNotNone(lib)

    def test_all_chosen_models_are_explicit(self):
        self.assertEqual(len(HAMLIB_MODELS),13)
        self.assertEqual(HAMLIB_MODELS['FTX-1'][0],1051)
        self.assertEqual(HAMLIB_MODELS['TS-990S'][0],2039)

    def test_open_verify_mode_and_ptt(self):
        lib=FakeLibrary();ctl=HamlibController('FT-710')
        with patch('psrtty.hamlib_radio.load_library',return_value=(lib,None)):
            self.assertTrue(ctl.connect('COM7',38400).connected)
            self.assertEqual(lib.events[:4],[('model',1049),('conf',1,b'COM7'),('conf',2,b'38400'),('open',123)])
            self.assertTrue(ctl.set_data_mode('LSB-D'))
            self.assertTrue(ctl.set_ptt(True))
            self.assertFalse(ctl.set_frequency(21_085_000))
            self.assertTrue(ctl.set_ptt(False))
            self.assertTrue(ctl.set_frequency(21_085_000))
            ctl.disconnect()
        self.assertEqual(lib.events[-2:],[('close',123),('cleanup',123)])

    def test_missing_explicit_port_fails_closed(self):
        ctl=HamlibController('TS-890S')
        self.assertFalse(ctl.connect('AUTO','AUTO').connected)


if __name__=='__main__':unittest.main()
