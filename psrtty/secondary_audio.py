"""Independent monitor output; no PTT and no blocking writes in the TX loop."""
from copy import deepcopy
import math
import threading
import numpy as np
from .audio_devices import resolve_device
from .i18n import tr


def normalize_settings(value):
    value = value if isinstance(value, dict) else {}
    try:
        gain = float(value.get('gain', 1.0))
        if not math.isfinite(gain): gain = 1.0
    except (TypeError, ValueError):
        gain = 1.0
    return {'enabled': value.get('enabled') is True,
            'device': deepcopy(value.get('device', 'UNSET')),
            'gain': max(0.0, min(2.0, gain))}


class SecondaryOutput:
    def __init__(self, sd, audio, settings, primary_device, sample_rate, extra, report):
        self.sd, self.audio = sd, audio
        self.settings = normalize_settings(settings)
        self.position = 0
        self.stream = None
        self.done = threading.Event()
        self.report = report
        self.failed = False
        if not self.settings['enabled']:
            return
        try:
            if self.settings['device'] in (None, 'UNSET'):
                raise ValueError(tr('第二AudioOUTの出力先を選択してください。'))
            chosen = resolve_device(sd, self.settings['device'], 'output')
            # AUTO may resolve to None on non-Windows platforms.
            if primary_device is None:
                primary_device = sd.default.device[1]
            if chosen is None: chosen = sd.default.device[1]
            if chosen == primary_device:
                raise ValueError(tr('第二AudioOUTには主AudioOUTと別の出力先を選択してください。'))
            self.stream = sd.OutputStream(device=chosen, samplerate=sample_rate,
                channels=1, dtype='float32', blocksize=960, latency='low',
                callback=self.callback, **extra)
            self.stream.start()
        except Exception as exc:
            self.error(exc)
            self.close()

    def error(self, exc):
        if not self.failed:
            self.failed = True
            self.report(tr('第二AudioOUTを停止しました。出力先と接続を確認してください。') + ' ' + str(exc))

    def callback(self, outdata, frames, time_info, status):
        outdata.fill(0)
        if self.failed:
            self.done.set()
            raise self.sd.CallbackAbort
        if status:
            self.error(str(status))
            self.done.set()
            raise self.sd.CallbackAbort
        count = min(frames, len(self.audio) - self.position)
        if count > 0:
            samples = self.audio[self.position:self.position + count]
            outdata[:count, 0] = np.clip(samples * self.settings['gain'], -1.0, 1.0)
            self.position += count
        if self.position >= len(self.audio):
            self.done.set()
            raise self.sd.CallbackStop

    def close(self, drain=False):
        if self.stream is not None:
            stream, self.stream = self.stream, None
            try:
                if drain and not self.failed:
                    stream.stop()
                else:
                    stream.abort()
            except Exception as exc:
                self.error(exc)
            finally:
                try: stream.close()
                except Exception as exc: self.error(exc)


def same_device(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return all(a.get(key) == b.get(key) for key in ('backend', 'id', 'kind'))
    return a == b


def secondary_choices(primary):
    from .audio_engine import sd
    from .audio_devices import enumerate_devices
    rows = enumerate_devices(sd, 'output')
    try:
        index = resolve_device(sd, primary, 'output')
    except Exception:
        if primary in (None, '', 'AUTO'):
            raise ValueError(tr('主AudioOUTの自動出力先を確認できません。出力先を明示して保存してください。'))
        index = None
    if primary in (None, '', 'AUTO') and index is None:
        raise ValueError(tr('主AudioOUTの自動出力先を確認できません。出力先を明示して保存してください。'))
    choices, excluded = [], [primary]
    for row in rows:
        if (index is not None and row['index'] == index) or same_device(row['choice'], primary):
            excluded.append(row['choice'])
        else:
            choices.append((row['choice'], row['label']))
    return choices, excluded
