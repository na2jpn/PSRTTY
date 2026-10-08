"""Connection capabilities for the 1.09 additions. ICOM always uses CI-V."""
ICOM_EXTERNAL_AUDIO = {'IC-756PRO': 92, 'IC-756PROII': 100, 'IC-756PROIII': 110, 'IC-703': 104, 'IC-7000': 112, 'IC-746': 86, 'IC-7400 / IC-746PRO': 102, 'IC-7700': 116, 'IC-7800': 106, 'IC-910 / IC-910H': 96}
ICOM_EXTERNAL_PTT = {'IC-706': 72, 'IC-706MkII': 78, 'IC-706MkIIG': 88, 'IC-707': 62, 'IC-78': 98, 'IC-718': 94, 'IC-725': 40, 'IC-726': 48, 'IC-728': 56, 'IC-729': 58, 'IC-735': 4, 'IC-736': 64, 'IC-737': 60, 'IC-738': 68, 'IC-756': 80, 'IC-761': 30, 'IC-765': 44, 'IC-775': 70, 'IC-781': 38, 'IC-271': 32, 'IC-275': 16, 'IC-375': 18, 'IC-471': 34, 'IC-475': 20, 'IC-575': 22, 'IC-820H': 66, 'IC-821H': 76, 'IC-970': 46, 'IC-1275': 24}
LEGACY_FREQUENCY = {'IC-735', 'IC-820H', 'IC-821H'}
LEGACY_MODE = set(ICOM_EXTERNAL_PTT) | {'IC-756PRO', 'IC-756PROII', 'IC-756PROIII', 'IC-746', 'IC-910 / IC-910H', 'IC-7800'}
CAT_CABLE_MODELS = {'FT-817 / FT-817ND', 'FT-818ND', 'FT-857 / FT-857D'}

def connection_note(model):
    from .i18n import tr
    if model in ICOM_EXTERNAL_PTT:
        return tr('ui.c79c269d9e540a84')
    if model in ICOM_EXTERNAL_AUDIO:
        return tr('ui.f61962cfc1e2a168')
    if model in CAT_CABLE_MODELS:
        return tr('ui.4a4b529cf5e65f11')
    return ''
