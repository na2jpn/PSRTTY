"""Shared Audio OUT / main-window ALC indication."""
import math

def signature(radio,device):
    return [str(radio.get(k,'')) for k in ('model','com_port','civ_baud','civ_address','ptt','stopbits','auto_data_mode')]+[str(device or 'AUTO')]

def calibration_onset(audio,radio):
    c=audio.get('alc_calibration',{})
    if not isinstance(c,dict) or c.get('signature') != signature(radio,audio.get('output_device')):return None
    x=c.get('onset')
    return x if isinstance(x,(int,float)) and math.isfinite(x) and 0<x<=200 else None

def classify(value,gain,onset):
    if value is None:return False,'#a59d92'
    good=onset is not None and onset-5 <= gain < onset and value <= 1
    return good, '#208341' if good else '#c0392b' if value>=10 else '#c98722'
