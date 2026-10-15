"""Verified model instructions plus conservative guidance for other radios."""
from html import escape
from ..i18n import tr
from ..fsk_models import USB_KEYING,USB_AB,ACC13,ACC8,AFSK_ONLY,NO_REVERSE,KENWOOD_FSK,YAESU_FSK,YAESU_AFSK_ONLY,YAESU_USB,YAESU_EXTERNAL,warning_key,modes_for
from ..fsk_manuals import MANUALS,KENWOOD_MANUALS,YAESU_MANUALS,YAESU_EXTRA_MANUALS
from .fsk_yaesu import rows_and_note
from .fsk_notice import notice_html,notice_color,BLACK

def table(headings,rows):
    def cell(value,header=False):
        tag='th' if header else 'td'
        return f'<{tag} align="left" style="padding:5px;">{escape(str(value))}</{tag}>'
    return '<table border="1" cellspacing="0" cellpadding="4" width="100%"><tr>'+''.join(cell(v,True) for v in headings)+'</tr>'+''.join('<tr>'+''.join(cell(v) for v in row)+'</tr>' for row in rows)+'</table>'

def settings_html(model,line='DTR',ptt='CI-V',inverted=False):
    heading=tr('fskhelp.settings')
    rows=[]
    if model in AFSK_ONLY|YAESU_AFSK_ONLY:
        manual=(MANUALS|YAESU_MANUALS)[model]
        return '<html><body>'+notice_html(model)+'<p><a href="'+escape(manual,quote=True)+'">'+escape(tr('fsk3.manual'))+' ('+escape(model)+')</a></p></body></html>'
    if model in USB_KEYING:
        key_value=('USB1 '+line+' / USB2 '+line) if model=='IC-7851' else ('USB1 (A) '+line+' / USB1 (B) '+line) if model=='IC-7610' else ('USB (A) '+line+' / USB (B) '+line) if model in USB_AB else line
        rows=[(tr('fskhelp.rtty_key'),key_value),(tr('fskhelp.cw_key'),'OFF'),
              ('USB SEND','OFF' if ptt=='CI-V' else ptt if ptt in ('RTS','DTR') else tr('fskhelp.check_manual')),
              (tr('fskhelp.mode'),'RTTY / RTTY-R'),(tr('fskhelp.shift'),'170 Hz'),(tr('fskhelp.mark'),'2125 Hz')]
        note=tr('fsk3.usb12') if model=='IC-7851' else ''
    elif model in ACC13 or model in ACC8:
        rows=[(tr('fskhelp.input'),'ACC (13-pin): RTTY / FSK' if model in ACC13 else 'ACC (1): RTTY / FSK'),
              (tr('fsk.port'),tr('fsk3.separate')),
              (tr('fskhelp.mode'),' / '.join(modes_for(model))),
              (tr('fskhelp.shift'),'170 Hz'),(tr('fskhelp.mark'),'2125 Hz'),
              (tr('fskhelp.ptt'),tr('fskhelp.no_overlap')),('Audio IN',tr('fskhelp.rx_generic'))]
        note=tr('fsk3.external')+' '+tr('fsk3.shared_ptt')
        if model in NO_REVERSE:note+=' '+tr('fsk3.legacy')
    elif model in KENWOOD_FSK:
        rows=[(tr('fskhelp.mode'),tr('fsk4.modes')),
              (tr('fskhelp.ptt'),tr('fskhelp.cat_ptt') if ptt=='CAT' else tr('fskhelp.external_ptt'))]
        if model=='TS-890S':
            rows+=[('CAT',tr('fsk4.standard')), (tr('fsk.output'),tr('fsk4.enhanced')),
                   ('Advanced 17 / 18 (Standard RTS / DTR)','Flow Control / Off'),
                   ('Advanced 19 (Enhanced RTS)','RTTY Keying' if line=='RTS' else 'Off'),
                   ('Advanced 20 (Enhanced DTR)','RTTY Keying' if line=='DTR' else 'Off')]
            note=tr('fsk4.ports')
        else:
            rows+=[(tr('fskhelp.input'),'ACC2: 2 RTTY / 4 GND'),
                   (tr('fsk.port'),tr('fsk3.separate')),
                   ('ACC2 PTT','13 SS / 12 GND')]
            note=tr('fsk3.shared_ptt')
        if model=='TS-590SG':
            rows+=[('50 FSK SHIFT','170 Hz'),('51 FSK KEY-DOWN POLARITY','Off / On'),('52 FSK TONE FREQUENCY','2125 Hz')]
        else:
            rows+=[('2-06 FSK Spacing','170 Hz'),('2-07 FSK Keying Polarity','Off / On'),('2-08 FSK Tone Frequency','2125 Hz')]
        rows+=[('Audio IN',tr('fskhelp.rx_generic'))]
    elif model=='FT-891':
        rows=[('CAT',tr('fskhelp.enhanced')), (tr('fsk.output'),tr('fskhelp.standard')),
              ('10-05 RTTY SHIFT PORT',line),('07-12 PC KEYING','RTS' if line=='DTR' else 'DTR'),('10-09 RTTY SHIFT FREQ','170 Hz'),
              ('10-10 RTTY MARK FREQ','2125 Hz'),('10-11 RTTY BFO','LSB'),
              ('10-07 RTTY POLARITY-T','NOR '+tr('fskhelp.initial')), (tr('fskhelp.ptt'),tr('fskhelp.cat_ptt') if ptt=='CAT' else tr('fskhelp.external_ptt')),
              (tr('fskhelp.mode'),'RTTY'),('Audio IN',tr('fskhelp.rx_audio'))]
        note=tr('fskhelp.ft_note')
    elif model in YAESU_FSK:
        rows,note=rows_and_note(model,line,ptt)
    else:
        rows=[(tr('fskhelp.input'),tr('fskhelp.check_manual')),
              (tr('fskhelp.ptt'),tr('fskhelp.no_overlap')),
              (tr('fskhelp.mode'),tr('fskhelp.generic_mode')),('Audio IN',tr('fskhelp.rx_generic'))]
        note=tr('fskhelp.generic')
    warning=notice_html(model) if model in MANUALS or model in KENWOOD_FSK|YAESU_FSK or model=='その他ICOM' else ''
    html=warning+'<h3>'+escape(heading)+'</h3>'+table((tr('fskhelp.item'),tr('fskhelp.value')),rows)+'<p>'+escape(note)+'</p>'
    if model in USB_AB:
        prefix='USB1' if model=='IC-7610' else 'USB'
        html+='<h3>'+escape(tr('fskhelp.ab_title'))+'</h3>'+table((tr('fskhelp.civ_side'),tr('fskhelp.rtty_key')),[('A',prefix+' (A) '+line),('B',prefix+' (B) '+line)])+'<p>'+escape(tr('fskhelp.ab_note'))+'</p>'
    html+='<h3>'+escape(tr('fskhelp.polarity'))+'</h3>'+table((tr('fskhelp.inversion'),line+' OFF',line+' ON'),[
        (tr('fskhelp.normal'),'Mark','Space'),(tr('fskhelp.reversed'),'Space','Mark')])
    html+='<p>'+escape(tr('fsk4.polarity' if model in KENWOOD_FSK else 'fsk5.polarity' if model in YAESU_FSK else 'fskhelp.polarity_note'))+'</p>'
    manual=KENWOOD_MANUALS.get(model) or MANUALS.get(model) or YAESU_MANUALS.get(model)
    if manual:
        html+='<p><a href="'+escape(manual,quote=True)+'">'+escape(tr('fsk3.manual'))+' ('+escape(model)+')</a></p>'
    if model in YAESU_EXTERNAL or model=='FT-991 / FT-991A':
        name='SCU-17' if model in YAESU_EXTERNAL else 'FT-991A'
        html+='<p><a href="'+escape(YAESU_EXTRA_MANUALS[name],quote=True)+'">'+escape(tr('fsk3.manual'))+' ('+name+')</a></p>'
    return '<html><body>'+html+'</body></html>'


def icom_guide_html():
    html='<h3>ICOM</h3><p style="color:'+BLACK+';">'+escape(tr('fsk3.scope'))+'</p>'
    for key,models in (('usb_group',USB_KEYING),('acc_group',ACC13|ACC8),('afsk_group',AFSK_ONLY)):
        html+='<h3>'+escape(tr('fsk3.'+key))+'</h3>'
        representative={'usb_group':'IC-7300','acc_group':'IC-7100','afsk_group':'IC-707'}[key]
        html+=notice_html(representative)+'<ul>'
        for model in sorted(models):
            html+='<li><a style="color:'+notice_color(model)+';" href="'+escape(MANUALS[model],quote=True)+'">'+escape(model)+'</a></li>'
        html+='</ul>'
    html+='<p>'+escape(tr('fsk3.usb12'))+'</p>'
    return html


def kenwood_guide_html():
    html='<h3>Kenwood</h3><p>'+escape(tr('fsk4.modes'))+'</p>'
    for model in sorted(KENWOOD_FSK):
        html+='<h3 style="color:'+notice_color(model)+';">'+escape(model)+'</h3>'+settings_html(model,ptt='CAT').split('<body>',1)[1].rsplit('</body>',1)[0]
    return html


def yaesu_guide_html():
    html='<h3>Yaesu</h3><p>'+escape(tr('fsk3.scope'))+'</p>'
    for model in sorted(YAESU_FSK|YAESU_AFSK_ONLY):
        html+='<h3 style="color:'+notice_color(model)+';">'+escape(model)+'</h3>'+settings_html(model,ptt='CAT').split('<body>',1)[1].rsplit('</body>',1)[0]
    return html
