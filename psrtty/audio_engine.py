from __future__ import annotations

import threading
import time
import sys
from collections.abc import Callable

import numpy as np

from .decoder import RTTYDecoder
from .audio_devices import enumerate_devices, resolve_device
from .rtty_codec import encode_text_audio

try:
    import sounddevice as sd  # type: ignore
except Exception:  # pragma: no cover
    sd = None


class AudioEngine:
    def __init__(
        self,
        sample_rate: int = 48000,
        on_char: Callable[[str], None] | None = None,
        on_level: Callable[[float], None] | None = None,
        on_spectrum: Callable[[np.ndarray, np.ndarray], None] | None = None,
    ):
        self.sample_rate = sample_rate
        self.on_char = on_char or (lambda _c: None)
        self.on_level = on_level or (lambda _v: None)
        self.on_spectrum = on_spectrum or (lambda _f, _p: None)
        self._decode_lock = threading.RLock()
        self.decode_enabled = True
        self.decode_generation = 0
        self.decoder = RTTYDecoder(sample_rate=sample_rate, on_char=self.on_char)
        self.stream = None
        self.rx_gain = 1.0
        self._fft_buf = np.zeros(0, dtype=np.float32)
        self._last_fft = 0.0
        self.scope_enabled = False
        self.scope_frame = None
        self._tx_lock = threading.Lock()
        self._tx_active = False
        self._tx_cancel = threading.Event()
        self._tx_thread = None

    @staticmethod
    def is_available() -> bool:
        return sd is not None

    @staticmethod
    def devices(kind):
        return [(row['choice'], row['label']) for row in enumerate_devices(sd, kind)]

    def configure_decoder(self, baud: float, mark: float, space: float, invert: bool) -> None:
        with self._decode_lock:
            self.decoder.configure(baud, mark, space, invert)
            self.scope_frame = None

    def set_decode_enabled(self, enabled):
        with self._decode_lock:
            self.decode_enabled = bool(enabled)
            self.decode_generation += 1
            self.decoder.reset()

    def set_decode_sq(self, value):
        with self._decode_lock:
            self.decoder.sq_level = max(0, min(10, int(value)))
            self.decode_generation += 1
            self.decoder.reset()

    def set_rx_gain(self, gain: float) -> None:
        self.rx_gain = max(0.05, float(gain))

    def start_input(self, device: str | int | None = None) -> tuple[bool, str]:
        if device == 'UNSET':
            self.stop_input()
            return False, 'Audio IN: 未設定'
        if sd is None:
            return False, "sounddeviceがインストールされていません"
        self.stop_input()
        try:
            chosen = resolve_device(sd, device, "input")
            self.stream = sd.InputStream(
                device=chosen,
                channels=1,
                samplerate=self.sample_rate,
                dtype="float32",
                blocksize=960,
                callback=self._input_callback,
                **({'extra_settings': sd.WasapiSettings(auto_convert=True)} if sys.platform == 'win32' else {}),
            )
            self.stream.start()
            return True, "Audio入力開始"
        except Exception as e:
            if self.stream is not None:
                try:
                    self.stream.close()
                except Exception:
                    pass
            self.stream = None
            return False, f"Audio入力を開始できません: {e}"

    def stop_input(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
            except Exception:
                pass
            try:
                self.stream.close()
            except Exception:
                pass
        self.stream = None
        self.scope_frame = None
        self._fft_buf = np.zeros(0, dtype=np.float32)

    def _input_callback(self, indata, frames, time_info, status) -> None:  # pragma: no cover - hardware callback
        samples = np.asarray(indata[:, 0], dtype=np.float32) * self.rx_gain
        rms = float(np.sqrt(np.mean(samples * samples) + 1e-12))
        self.on_level(min(1.0, rms * 8.0))
        with self._decode_lock:
            if self.decode_enabled: self.decoder.feed(samples)
        self._fft_buf = np.concatenate((self._fft_buf, samples))[-8192:]
        now = time.monotonic()
        if len(self._fft_buf) >= 4096 and now - self._last_fft >= 0.10:
            self._last_fft = now
            seg = self._fft_buf[-4096:]
            if self.scope_enabled:
                with self._decode_lock:
                    tones = (self.decoder.mark_hz, self.decoder.space_hz, self.decoder.baud)
                # Latest-only mailbox: no GUI events queued by the audio thread.
                self.scope_frame = (now, seg.copy(), tones)
            win = np.hanning(len(seg))
            spec = np.fft.rfft(seg * win)
            power = 20 * np.log10(2 * np.abs(spec) / win.sum() + 1e-9)
            freqs = np.fft.rfftfreq(len(seg), 1 / self.sample_rate)
            mask = freqs <= 4000
            self.on_spectrum(freqs[mask].astype(np.float32), power[mask].astype(np.float32))

    def stop_tx(self, ptt_off=None) -> None:
        self._tx_cancel.set()
        # Only the TX worker touches its output stream. Calling global sd.stop()
        # here races sd.wait()/stream.close() on another thread on Windows.

    def wait_tx(self, timeout=2.0):
        if self._tx_thread and self._tx_thread is not threading.current_thread():
            self._tx_thread.join(timeout)

    def send_text(
        self,
        text: str,
        output_device: str | int | None,
        baud: float,
        mark: float,
        space: float,
        invert: bool,
        amplitude: float,
        ptt_on: Callable[[], None] | None = None,
        ptt_off: Callable[[], None] | None = None,
        on_finished: Callable[[bool, str], None] | None = None,
    ) -> tuple[bool, str]:
        if sd is None:
            return False, "sounddeviceがインストールされていません"
        if self._tx_active:
            return False, "送信中です"
        audio = encode_text_audio(
            text,
            sample_rate=self.sample_rate,
            baud=baud,
            mark_hz=mark,
            space_hz=space,
            invert=invert,
            amplitude=max(0.01, min(0.95, amplitude)),
        )
        try:
            chosen = resolve_device(sd, output_device, 'output')
        except Exception as exc:
            return False, str(exc)

        self._tx_active = True
        self._tx_cancel.clear()

        def worker():  # hardware calls are exercised with fake sounddevice in tests
            output = None
            success = False
            message = "送信中止"
            try:
                if self._tx_cancel.is_set():
                    return
                if not ptt_on or ptt_on() is not True:
                    raise RuntimeError("PTTを確認できないため送信しませんでした")
                if self._tx_cancel.wait(0.12):
                    return
                if self._tx_cancel.is_set():
                    return
                output = sd.OutputStream(samplerate=self.sample_rate, device=chosen,
                    channels=1, dtype='float32', blocksize=960, latency='low',
                    **({'extra_settings': sd.WasapiSettings(auto_convert=True)} if sys.platform == 'win32' else {}))
                output.start()
                for offset in range(0, len(audio), 960):
                    if self._tx_cancel.is_set():
                        return
                    output.write(audio[offset:offset+960].reshape(-1, 1))
                if self._tx_cancel.is_set():
                    return
                output.stop()  # Drain normal playback before unkeying.
                if not self._tx_cancel.wait(0.08):
                    success = True
                    message = "送信完了"
            except Exception as exc:
                message = f"送信失敗: {exc}"
            finally:
                if output is not None and not success:
                    try:
                        output.abort()
                    except Exception as exc:
                        message = f'音声停止失敗: {exc}'
                try:
                    if ptt_off and ptt_off() is False:
                        success = False
                        message = 'PTT解除を確認できません。無線機を確認してください。'
                except Exception as exc:
                    success = False
                    message = f'PTT解除失敗: {exc}'
                finally:
                    if output is not None:
                        try:
                            output.close()
                        except Exception as exc:
                            success = False
                            message = f'音声終了失敗: {exc}'
                    self._tx_active = False
                    if on_finished:
                        on_finished(success, message)

        self._tx_thread = threading.Thread(target=worker, daemon=True)
        self._tx_thread.start()
        return True, "送信開始"
