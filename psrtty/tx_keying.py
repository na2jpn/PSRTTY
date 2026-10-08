"""Shared normal/test/live keying, preserving pre-key profiles."""
from .i18n import tr

def keying_callbacks(controller, mode, sequencer, ready):
    external = mode == '外部接続'
    if external and (not sequencer.config.get('enabled') or sequencer.config.get('role') != 'ptt'):
        raise ValueError(tr('ui.3e8772d73f01525a'))
    if not external and sequencer.config.get('enabled') and sequencer.config.get('role') == 'ptt':
        raise ValueError(tr('ui.53874a42d9a74e7a'))
    ptt = {'CI-V': controller.set_ptt, 'CAT': controller.set_ptt, 'RTS': controller.set_rts, 'DTR': controller.set_dtr}.get(mode)
    def on():
        if not ready() or not sequencer.before_ptt(): return False
        if external:
            controller.external_transmitting = True
            return True
        return bool(ptt and ptt(True))
    def off():
        try:
            return True if external else bool(ptt and ptt(False))
        finally:
            try: sequencer.after_ptt()
            finally:
                if external: controller.external_transmitting = False
    return on, off
