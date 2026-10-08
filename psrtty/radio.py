from .i18n import tr
"""Factory preserving ICOM CI-V and isolating experimental CAT support."""
from .civ import CIVController, radio_address, connect_configured
from .config import RIG_MODELS
from .yaesu import YAESU_MODELS, YaesuController
from .hamlib_radio import HAMLIB_MODELS, HamlibController


def validate_radio(values):
    model = values.get('model', '')
    if model in HAMLIB_MODELS:
        if values.get('ptt','CAT')!='CAT':
            raise ValueError(tr('ui.4974a6628eaba1f2'))
        if str(values.get('com_port','AUTO')).upper()=='AUTO' or str(values.get('cat_baud','AUTO')).upper()=='AUTO':
            raise ValueError(tr('ui.c3e19a59664aae88'))
    elif model in YAESU_MODELS:
        if values.get('ptt', 'CAT') != 'CAT':
            raise ValueError(tr('ui.e24ce7516cfa999a'))
        if int(values.get('cat_stopbits', 1 if model == 'FTX-1' else 2)) not in (1, 2):
            raise ValueError(tr('ui.8c2f1f21557e9eeb'))
    elif model in RIG_MODELS:
        radio_address(values)
        from .radio_support import ICOM_EXTERNAL_PTT
        if model in ICOM_EXTERNAL_PTT and values.get('ptt') != '外部接続':
            raise ValueError(tr('ui.bff9cda88ed38009'))
    else:
        raise ValueError(tr('ui.451f6fe5ab7125c4'))


def create_controller(values):
    validate_radio(values)
    if values['model'] in HAMLIB_MODELS:
        return HamlibController(values['model'])
    return CIVController(radio_address(values), model=values['model'])
