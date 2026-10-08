"""Optional pre-key line for an external amplifier or preamplifier."""
from __future__ import annotations
from .i18n import tr

import time

try:
    import serial
except ImportError:  # The connection test reports this as a configuration error.
    serial = None


def validate_external(config, radio_port=''):
    if not config.get('enabled', False):
        return
    port = str(config.get('com_port', '')).strip().upper()
    if not port or port == 'AUTO':
        raise ValueError(tr('ui.908b9e45ca21eaf5'))
    if port == str(radio_port).strip().upper():
        raise ValueError(tr('ui.ccab6781bcc1fc2a'))
    if config.get('line') not in ('RTS', 'DTR'):
        raise ValueError(tr('ui.dfab275ee9970e4a'))
    if config.get('role', 'prekey') not in ('prekey', 'ptt'):
        raise ValueError(tr('ui.e264011bdc01fdf0'))
    delay = float(config.get('delay_seconds', 0))
    if not 0.1 <= delay <= 9.9:
        raise ValueError(tr('ui.90670eb97cfca458'))


class ExternalPTT:
    def __init__(self, config, radio_port='', cancel=None):
        self.config = dict(config)
        validate_external(self.config, radio_port)
        self.cancel = cancel
        self.serial = None

    def before_ptt(self):
        if not self.config.get('enabled', False):
            return True
        if serial is None:
            raise RuntimeError(tr('ui.0452672f31d4f348'))
        line = self.config['line'].lower()
        active = not bool(self.config.get('reversed', False))
        try:
            device = serial.Serial(port=None, timeout=.1, write_timeout=.3,
                                   rtscts=False, dsrdtr=False)
            setattr(device, line, not active)
            self.serial = device
            device.port = self.config['com_port']
            device.open()
            setattr(device, line, active)
            duration = 0 if self.config.get('role') == 'ptt' else float(self.config['delay_seconds'])
            if self.cancel is not None:
                if self.cancel.wait(duration):
                    self.after_ptt()
                    return False
            else:
                time.sleep(duration)
            return True
        except Exception:
            self.after_ptt()
            raise

    def after_ptt(self):
        device, self.serial = self.serial, None
        if device is None:
            return True
        try:
            setattr(device, self.config['line'].lower(), bool(self.config.get('reversed', False)))
        finally:
            device.close()
        return True
