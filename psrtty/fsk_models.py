"""FSK capabilities, independent of CAT/audio support. See docs/FSK_ICOM_118_FIX3.md."""
# USB signal routing is configured manually in the radio, never guessed from COM numbers.
USB_KEYING = frozenset(('IC-705','IC-7300','IC-7300MK2','IC-905',
    'IC-9700','IC-7610','IC-7760','IC-7851'))
USB_AB = USB_KEYING - {'IC-7300','IC-7851'}
ACC13 = frozenset(('IC-7200','IC-7410','IC-7100','IC-9100','IC-703','IC-7000','IC-706',
    'IC-706MkII','IC-706MkIIG','IC-78','IC-718'))
ACC8 = frozenset(('IC-7600','IC-756PRO','IC-756PROII','IC-756PROIII',
    'IC-746','IC-7400 / IC-746PRO','IC-7700','IC-7800','IC-756',
    'IC-761','IC-765','IC-775','IC-781'))
ICOM_FSK = USB_KEYING | ACC13 | ACC8
# These manuals describe AFSK operation; they have no native RTTY/FSK input/mode.
AFSK_ONLY = frozenset(('IC-910 / IC-910H','IC-707','IC-725','IC-726','IC-728','IC-729',
    'IC-735','IC-736','IC-737','IC-738','IC-271','IC-275','IC-375','IC-471',
    'IC-475','IC-575','IC-820H','IC-821H','IC-970','IC-1275'))
NO_REVERSE = frozenset(('IC-761','IC-765','IC-781'))
KENWOOD_FSK = frozenset(('TS-590SG','TS-890S','TS-990S'))
# TS-890S USB keying uses a separate virtual COM, never the Hamlib CAT handle.
KENWOOD_USB = frozenset(('TS-890S',))
YAESU_USB = frozenset(('FT-891','FT-991 / FT-991A','FTX-1','FT-710',
    'FTDX10','FTDX101D','FTDX101MP','FTDX3000'))
YAESU_EXTERNAL = frozenset(('FT-450','FT-950'))
YAESU_FSK = YAESU_USB | YAESU_EXTERNAL
YAESU_AFSK_ONLY = frozenset(('FT-817 / FT-817ND','FT-818ND','FT-857 / FT-857D'))
def modes_for(model):
    if model in NO_REVERSE:return ('RTTY',)
    if model in ICOM_FSK or model in KENWOOD_FSK or model in YAESU_FSK:return ('RTTY','RTTY-R')
    return ()

def warning_key(model):
    if model in YAESU_USB:return 'fsk5.usb'
    if model in YAESU_EXTERNAL:return 'fsk5.external'
    if model in YAESU_AFSK_ONLY:return 'fsk3.afsk_only'
    if model in KENWOOD_USB:return 'fsk4.usb'
    if model in KENWOOD_FSK:return 'fsk4.external'
    if model in AFSK_ONLY:return 'fsk3.afsk_only'
    if model in ACC13 or model in ACC8:return 'fsk3.external'
    if model in USB_KEYING:return 'fsk3.usb'
    return 'fsk3.unverified'
