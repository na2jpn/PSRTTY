"""Offline dual output: each device owns its stream and never controls PTT."""
import threading
import sys
import numpy as np
from .audio_devices import resolve_device
from .secondary_audio import normalize_settings
from .i18n import tr


def start_offline_dual(engine, sd, audio, primary_device, on_finished):
    secondary = normalize_settings(engine.secondary_settings)
    engine._tx_active = True
    engine._tx_cancel.clear()
    engine.secondary_notice = ''
    lock = threading.Lock()
    claimed = set()
    completed = []
    errors = []

    def playback(label, selection, is_secondary):
        stream = None
        success = False
        try:
            if engine._tx_cancel.is_set(): return
            if selection == 'UNSET' or (is_secondary and selection is None):
                raise ValueError(tr('未設定'))
            chosen = resolve_device(sd, selection, 'output')
            identity = chosen
            if identity is None:
                try: identity = sd.default.device[1]
                except (AttributeError, TypeError, IndexError): pass
            with lock:
                if identity in claimed: return
                claimed.add(identity)
            stream = sd.OutputStream(device=chosen, samplerate=engine.sample_rate,
                channels=1, dtype='float32', blocksize=960, latency='low',
                **({'extra_settings': sd.WasapiSettings(auto_convert=True)} if sys.platform == 'win32' else {}))
            if engine._tx_cancel.is_set(): return
            stream.start()
            for offset in range(0, len(audio), 960):
                if engine._tx_cancel.is_set(): return
                gain = secondary['gain'] if is_secondary else engine.tx_gain
                stream.write(np.clip(audio[offset:offset+960] * gain, -1, 1).reshape(-1, 1))
            if engine._tx_cancel.is_set(): return
            stream.stop()
            success = not engine._tx_cancel.is_set()
        except Exception as exc:
            with lock:
                errors.append(label + ': ' + str(exc))
        finally:
            if stream is not None:
                try:
                    if not success: stream.abort()
                except Exception as exc:
                    with lock: errors.append(label + ': ' + str(exc))
                finally:
                    try: stream.close()
                    except Exception as exc:
                        success = False
                        with lock: errors.append(label + ': ' + str(exc))
            with lock:
                completed.append(success)
                if errors:
                    engine.secondary_notice = tr('未接続時の音声出力：使えない出力先があります。') + ' ' + ' / '.join(errors)

    def worker():
        jobs = []
        try:
            for label, selection, is_secondary in (
                    ('Audio OUT', primary_device, False),
                    ('Audio OUT 2', secondary['device'], True)):
                thread = threading.Thread(target=playback, args=(label, selection, is_secondary), daemon=True)
                thread.start(); jobs.append(thread)
            for thread in jobs: thread.join()
            success = any(completed) and not engine._tx_cancel.is_set()
            message = tr('送信完了') if success else tr('送信中止') if engine._tx_cancel.is_set() else tr('両方のAudioOUTを使用できません。出力先と接続を確認してください。') + ' ' + ' / '.join(errors)
        except Exception as exc:
            engine._tx_cancel.set()
            for thread in jobs: thread.join()
            success, message = False, str(exc)
        finally:
            engine._tx_active = False
            if on_finished: on_finished(success, message)

    engine._tx_thread = threading.Thread(target=worker, daemon=True)
    engine._tx_thread.start()
    return True, tr('送信開始')
