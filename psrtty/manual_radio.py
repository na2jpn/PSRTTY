"""External PTT without CAT; no invented frequency or meter readings."""
from .civ import CIVController, CIVStatus
from .i18n import tr

MANUAL_MODEL = 'EXTERNAL-MANUAL'


class ManualController(CIVController):
    def __init__(self):
        super().__init__(0, model=MANUAL_MODEL)
        self.manual = True
        self.external_transmitting = False

    def connect(self, port='AUTO', baud='AUTO', timeout=8.0):
        self.cancel.clear()
        self.status = CIVStatus(True, '', 0, None, tr('v117.manual'))
        return self.status

    def disconnect(self):
        self.cancel.set()
        self.external_transmitting = False
        self.status = CIVStatus()

    def read_frequency(self): return None
    def read_transmitting(self): return self.external_transmitting
    def set_data_mode(self, mode): return True
    def set_operating_mode(self, mode): return True
    def set_ptt(self, on): return False
    def set_rts(self, on): return False
    def set_dtr(self, on): return False
