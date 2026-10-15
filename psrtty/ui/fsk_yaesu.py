"""Yaesu manufacturer settings. Internal RTTY/RTTY-R are Hamlib mode names."""
from ..i18n import tr
from ..fsk_models import YAESU_USB


def rows_and_note(model,line,ptt):
    other='RTS' if line=='DTR' else 'DTR'
    rows=[(tr('fskhelp.mode'),tr('fsk5.ft450_mode' if model=='FT-450' else 'fsk5.modes')),
          (tr('fskhelp.ptt'),tr('fskhelp.cat_ptt') if ptt=='CAT' else tr('fskhelp.external_ptt'))]
    if model in YAESU_USB:
        rows+=[('CAT',tr('fsk5.enhanced')),(tr('fsk.output'),tr('fsk5.standard'))]
        note=tr('fsk5.pair')
        if model=='FT-991 / FT-991A':
            rows+=[('060 PC KEYING',other),
                   ('RTTY SHIFT PORT: FT-991 098 / FT-991A 096',line),
                   ('RTTY POLARITY-TX: FT-991 100 / FT-991A 098','NOR'),
                   ('RTTY SHIFT FREQ: FT-991 102 / FT-991A 100','170 Hz'),
                   ('RTTY MARK FREQ: FT-991 103 / FT-991A 101','2125 Hz')]
        elif model=='FTDX3000':
            rows+=[('093 RTTY SHIFT PORT','USB'),('065 PC KEYING',other),
                   ('095 POLARITY-T','NOR'),('097 RTTY SHIFT','170 Hz'),('098 RTTY MARK FREQ','2125 Hz')]
        else:
            rows+=[('RADIO SETTING → MODE RTTY → RPTT SELECT',other),
                   ('RADIO SETTING → MODE RTTY → POLARITY TX','NOR'),
                   ('RADIO SETTING → MODE RTTY → SHIFT FREQUENCY','170 Hz'),
                   ('RADIO SETTING → MODE RTTY → MARK FREQUENCY','2125 Hz')]
    else:
        rows+=[(tr('fskhelp.input'),'RTTY/PKT' if model=='FT-950' else 'DATA'),
               (tr('fsk.output'),'4 FSK IN / 2 GND'),('PTT','3 DATA PTT / 2 GND'),
               (tr('fsk.port'),tr('fsk3.separate'))]
        if model=='FT-450':
            rows+=[('D TYPE','RTTY'),('RTY SFT','170 Hz'),('RTY TON','2125 Hz'),('RTYTPOL','NOR')]
        else:
            rows+=[('062 RTTY SHIFT','170 Hz'),('063 RTTY TONE','2125 Hz'),('060 RTTY T PLRTY','nor')]
        note=tr('fsk5.scu17')+' '+tr('fsk3.shared_ptt')
    rows+=[('Audio IN',tr('fskhelp.rx_generic'))]
    return rows,note
