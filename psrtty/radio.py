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
            raise ValueError(tr('HamlibではCATによるPTTを選択してください。'))
        if str(values.get('com_port','AUTO')).upper()=='AUTO' or str(values.get('cat_baud','AUTO')).upper()=='AUTO':
            raise ValueError(tr('HamlibではCOMポートとCAT速度を指定してください。'))
    elif model in YAESU_MODELS:
        if values.get('ptt', 'CAT') != 'CAT':
            raise ValueError(tr('Yaesu試験対応はCATによるPTTを選んでください。'))
        if int(values.get('cat_stopbits', 1 if model == 'FTX-1' else 2)) not in (1, 2):
            raise ValueError(tr('ストップビットは1または2です。'))
    elif model in RIG_MODELS:
        radio_address(values)
    else:
        raise ValueError(tr('無線機を選択してください。'))


def create_controller(values):
    validate_radio(values)
    if values['model'] in HAMLIB_MODELS:
        return HamlibController(values['model'])
    return CIVController(radio_address(values), model=values['model'])
