"""Connection guidance: USB-only black, external equipment blue, AFSK-only red."""
from html import escape
from ..i18n import tr
from ..fsk_models import (USB_KEYING,KENWOOD_USB,YAESU_USB,ACC13,ACC8,
    KENWOOD_FSK,YAESU_EXTERNAL,AFSK_ONLY,YAESU_AFSK_ONLY,warning_key)

BLACK='#000000'
BLUE='#1565c0'
RED='#bd241c'
# FT-891 has USB CAT/FSK, but receive audio needs a separate connection.
USB_ONLY=USB_KEYING|KENWOOD_USB|(YAESU_USB-{'FT-891'})
EXTERNAL=ACC13|ACC8|(KENWOOD_FSK-KENWOOD_USB)|YAESU_EXTERNAL|{'FT-891'}
AFSK_REQUIRED=AFSK_ONLY|YAESU_AFSK_ONLY

def notice_color(model):
    if model in AFSK_REQUIRED:return RED
    if model in EXTERNAL:return BLUE
    return BLACK

def notice_key(model):
    if model in USB_ONLY:return 'fsk6.usb'
    if model=='FT-891':return 'fsk6.audio'
    return warning_key(model)

def notice_html(model):
    text=escape(tr(notice_key(model)))
    if model in AFSK_REQUIRED:text='<b>'+text+'</b>'
    return '<p style="color:'+notice_color(model)+';">'+text+'</p>'
