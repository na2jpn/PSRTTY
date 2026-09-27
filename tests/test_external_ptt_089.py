import unittest
from unittest.mock import patch
from types import SimpleNamespace

from psrtty.external_ptt import ExternalPTT, validate_external


class Port:
    def __init__(self, **kwargs):
        self.events = []
        self.port = None
    def __setattr__(self, name, value):
        if name in ('rts', 'dtr') and hasattr(self, 'events'):
            self.events.append((name, value))
        object.__setattr__(self, name, value)
    def open(self): self.events.append(('open', self.port))
    def close(self): self.events.append(('close', None))


class ExternalTest(unittest.TestCase):
    def test_active_and_release_order(self):
        config = {'enabled': True, 'com_port': 'COM9', 'line': 'RTS', 'reversed': False, 'delay_seconds': .1}
        port = Port()
        with patch('psrtty.external_ptt.serial', SimpleNamespace(Serial=lambda **kw: port)), patch('psrtty.external_ptt.time.sleep') as sleep:
            key = ExternalPTT(config, 'COM3')
            self.assertTrue(key.before_ptt())
            self.assertEqual(port.events[:3], [('rts', False), ('open', 'COM9'), ('rts', True)])
            sleep.assert_called_once_with(.1)
            self.assertTrue(key.after_ptt())
        self.assertEqual(port.events[-2:], [('rts', False), ('close', None)])

    def test_reversed_and_separate_port(self):
        config = {'enabled': True, 'com_port': 'COM9', 'line': 'DTR', 'reversed': True, 'delay_seconds': 9.9}
        with self.assertRaisesRegex(ValueError, '別のCOM'):
            validate_external(config, 'com9')
        port = Port()
        with patch('psrtty.external_ptt.serial', SimpleNamespace(Serial=lambda **kw: port)), patch('psrtty.external_ptt.time.sleep'):
            key = ExternalPTT(config, 'COM3')
            key.before_ptt(); key.after_ptt()
        self.assertEqual([value for line, value in port.events if line == 'dtr'], [True, False, True])


if __name__ == '__main__': unittest.main()
