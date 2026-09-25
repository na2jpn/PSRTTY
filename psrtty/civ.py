from __future__ import annotations

import threading
import time
from dataclasses import dataclass

try:
    import serial  # type: ignore
    from serial.tools import list_ports  # type: ignore
except Exception:  # pragma: no cover - optional until installed on target
    serial = None
    list_ports = None


@dataclass
class CIVStatus:
    connected: bool = False
    port: str = ""
    baud: int = 0
    frequency_hz: int | None = None
    message: str = "未接続"


def decode_bcd_frequency(data: bytes) -> int:
    digits: list[int] = []
    for b in data:
        digits.append(b & 0x0F)
        digits.append((b >> 4) & 0x0F)
    value = 0
    for power, digit in enumerate(digits):
        if digit > 9:
            raise ValueError("invalid BCD")
        value += digit * (10 ** power)
    return value


class CIVController:
    PC_ADDRESS = 0xE0

    def __init__(self, civ_address: int, model: str = ""):
        self.model = model
        self.address = civ_address & 0xFF
        self.ser = None
        self.status = CIVStatus()
        self._lock = threading.RLock()
        self.cancel = threading.Event()
        self._connect_deadline = None

    @staticmethod
    def available_ports() -> list[str]:
        if list_ports is None:
            return []
        return [p.device for p in list_ports.comports()]

    @staticmethod
    def port_choices():
        if list_ports is None:
            return []
        choices = []
        for p in sorted(list_ports.comports()):
            name = (p.description or '').strip()
            label = f'{p.device} — {name}' if name and name != 'n/a' else p.device
            choices.append((p.device, label))
        return choices

    def _frame(self, *payload: int) -> bytes:
        return bytes([0xFE, 0xFE, self.address, self.PC_ADDRESS, *payload, 0xFD])

    def _read_response(self, command: int | None = None, timeout: float = 0.55) -> bytes:
        """Read through command echoes and return a radio->PC CI-V frame."""
        if not self.ser:
            return b""
        deadline = time.monotonic() + timeout
        if self._connect_deadline is not None:
            deadline = min(deadline, self._connect_deadline)
        buf = bytearray()
        while time.monotonic() < deadline and not self.cancel.is_set():
            b = self.ser.read(1)
            if not b:
                continue
            buf += b
            if b != b"\xFD":
                continue
            # There may be an echoed PC->radio frame before the actual reply.
            starts = [i for i in range(max(0, len(buf) - 128), len(buf) - 1) if buf[i:i+2] == b"\xFE\xFE"]
            for idx in reversed(starts):
                frame = bytes(buf[idx:])
                if len(frame) < 6 or frame[-1] != 0xFD:
                    continue
                # response destination PC, source radio
                if frame[2] != self.PC_ADDRESS or frame[3] != self.address:
                    continue
                if command is None:
                    return frame
                if frame[4] == command or frame[4] in (0xFB, 0xFA):
                    return frame
            # retain only enough tail for a possible next frame
            if len(buf) > 256:
                buf = buf[-128:]
        return b""

    def connect(self, port: str = "AUTO", baud: str | int = "AUTO", timeout: float = 8.0) -> CIVStatus:
        self._connect_deadline = time.monotonic() + timeout
        try:
            return self._connect(port, baud)
        finally:
            self._connect_deadline = None

    def _connect(self, port, baud) -> CIVStatus:
        if serial is None:
            self.status = CIVStatus(False, message="pyserialがインストールされていません")
            return self.status
        ports = self.available_ports() if str(port).upper() == "AUTO" else [str(port)]
        if not ports:
            self.status = CIVStatus(False, message="COMポートが見つかりません")
            return self.status
        bauds = [115200, 57600, 38400, 19200, 9600, 4800] if str(baud).upper() == "AUTO" else [int(baud)]
        self.disconnect()
        for candidate in ports:
            for speed in bauds:
                if self.cancel.is_set() or time.monotonic() >= self._connect_deadline:
                    self.disconnect()
                    self.status.message = "接続を中止しました／タイムアウト（COMと速度の手動指定もお試しください）"
                    return self.status
                try:
                    s = serial.Serial(candidate, speed, timeout=0.05, write_timeout=0.3, rtscts=False, dsrdtr=False)
                    try:
                        s.rts = False
                        s.dtr = False
                    except Exception:
                        pass
                    self.ser = s
                    freq = self.read_frequency()
                    if not self.cancel.is_set() and freq and 100_000 <= freq <= 15_000_000_000:
                        self.status = CIVStatus(True, candidate, speed, freq, "接続")
                        return self.status
                    s.close()
                    self.ser = None
                except Exception:
                    if self.ser:
                        try:
                            self.ser.close()
                        except Exception:
                            pass
                    self.ser = None
        self.status = CIVStatus(False, message="CI-V応答を確認できませんでした")
        return self.status

    def disconnect(self) -> None:
        with self._lock:
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            self.status = CIVStatus(False, message="未接続")

    def read_frequency(self) -> int | None:
        with self._lock:
            if not self.ser:
                return None
            try:
                self.ser.reset_input_buffer()
                self.ser.write(self._frame(0x03))
                raw = self._read_response(0x03)
                if len(raw) < 7 or raw[4] != 0x03:
                    return None
                payload = raw[5:-1]
                if len(payload) not in (5, 6):
                    return None
                # IC-905 uses six BCD bytes in the 10 GHz band.
                freq = decode_bcd_frequency(payload)
                self.status.frequency_hz = freq
                return freq
            except Exception:
                return None

    def read_filter(self):
        """Read selected VFO mode, DATA flag and filter as one CI-V tuple."""
        with self._lock:
            if not self._control_ready(): return None
            # These models do not share the verified 26 00 mode/DATA tuple.
            if self.model in ("IC-7200", "IC-7410", "IC-7600", "IC-9100"): return None
            try:
                self.ser.reset_input_buffer(); self.ser.write(self._frame(0x26, 0x00))
                raw=self._read_response(0x26, timeout=.3)
                if len(raw)!=10 or raw[4:6]!=b'\x26\x00' or raw[7] not in (0,1) or raw[8] not in (1,2,3): return None
                return dict(kind='ICOM', mode=(raw[6],raw[7]), value=raw[8],
                            options=[(i,f'FIL{i}') for i in (1,2,3)], narrow=None)
            except Exception: return None

    def set_filter(self, value, expected):
        with self._lock:
            if not self._control_ready() or type(value) is not int or value not in (1,2,3): return False
            try:
                if self.read_transmitting() is not False: return False
                current=self.read_filter()
                if not current or not expected or current['mode']!=expected['mode']: return False
                mode,data=current['mode']
                self.ser.reset_input_buffer(); self.ser.write(self._frame(0x26,0,mode,data,value))
                raw=self._read_response(0x26, timeout=.3)
                if len(raw)<6 or raw[4]!=0xFB: return False
                actual=self.read_filter()
                return bool(actual and actual['mode']==current['mode'] and actual['value']==value)
            except Exception: return False

    FEATURES = {"NB": 0x22, "NR": 0x40, "AN": 0x41, "MN": 0x48}

    def _control_ready(self):
        return bool(self.ser and self.status.connected and not self.cancel.is_set())

    def read_feature(self, name):
        """None means unknown (including unsupported); never guess OFF."""
        with self._lock:
            if not self._control_ready() or name not in self.FEATURES: return None
            try:
                sub = self.FEATURES[name]
                self.ser.reset_input_buffer(); self.ser.write(self._frame(0x16, sub))
                raw = self._read_response(0x16, timeout=.25)
                if len(raw) == 8 and raw[4:6] == bytes([0x16, sub]) and raw[6] in (0, 1):
                    return bool(raw[6])
            except Exception:
                pass
            return None

    def read_transmitting(self):
        with self._lock:
            if not self._control_ready(): return None
            self.ser.reset_input_buffer(); self.ser.write(self._frame(0x1C, 0))
            raw = self._read_response(0x1C, timeout=.25)
            if len(raw) == 8 and raw[4:6] == b"\x1c\x00" and raw[6] in (0, 1):
                return bool(raw[6])
            return None

    def set_frequency(self, hz):
        with self._lock:
            if not self._control_ready() or type(hz) is not int or not 100000 <= hz < 15000000000:
                return False
            try:
                if self.read_transmitting() is not False: return False
                digits = f"{hz:012d}" if hz >= 10000000000 else f"{hz:010d}"
                bcd = bytes(int(digits[i:i+2], 16) for i in range(len(digits)-2, -1, -2))
                self.ser.reset_input_buffer(); self.ser.write(self._frame(0x05, *bcd))
                raw = self._read_response(0x05, timeout=.3)
                return len(raw) >= 6 and raw[4] == 0xFB
            except Exception:
                return False

    def set_feature(self, name, on):
        with self._lock:
            if not self._control_ready() or name not in self.FEATURES: return False
            try:
                if self.read_transmitting() is not False: return False
                self.ser.reset_input_buffer()
                self.ser.write(self._frame(0x16, self.FEATURES[name], int(bool(on))))
                raw = self._read_response(0x16, timeout=.3)
                return len(raw) >= 6 and raw[4] == 0xFB
            except Exception:
                return False

    def set_ptt(self, on: bool) -> bool:
        with self._lock:
            if not self.ser or not self.status.connected:
                return False
            try:
                self.ser.reset_input_buffer()
                self.ser.write(self._frame(0x1C, 0x00, 0x01 if on else 0x00))
                raw = self._read_response(0x1C, timeout=0.30)
                # A missing/rejected ACK must never authorize audio transmission.
                return len(raw) >= 6 and raw[4] == 0xFB
            except Exception:
                return False

    def set_rts(self, on: bool) -> bool:
        with self._lock:
            if not self.ser or not self.status.connected:
                return False
            try:
                self.ser.rts = bool(on)
                return True
            except Exception:
                return False

    def set_dtr(self, on: bool) -> bool:
        with self._lock:
            if not self.ser or not self.status.connected:
                return False
            try:
                self.ser.dtr = bool(on)
                return True
            except Exception:
                return False


    def set_data_mode(self, mode: str = "LSB-D") -> bool:
        """Select SSB and DATA ON using the model-specific command; FIL1."""
        if mode not in ("LSB-D", "USB-D"):
            raise ValueError("未対応のDATAモード")
        with self._lock:
            if not self.ser or not self.status.connected:
                return False
            try:
                data_sub = 0x04 if self.model == "IC-7200" else 0x06
                for payload in ((0x06, 0x00 if mode == "LSB-D" else 0x01), (0x1A, data_sub, 0x01, 0x01)):
                    self.ser.reset_input_buffer()
                    self.ser.write(self._frame(*payload))
                    raw = self._read_response(timeout=0.5)
                    if len(raw) < 6 or raw[4] != 0xFB:
                        return False
                return True
            except Exception:
                return False


def radio_address(settings: dict) -> int:
    if not settings.get("model"):
        raise ValueError("無線機を選択してください。")
    try:
        addr = int(settings.get("civ_address", ""), 16)
    except (TypeError, ValueError):
        raise ValueError("CI-Vアドレスは16進数で入力してください。") from None
    if not 1 <= addr < 0xE0:
        raise ValueError("CI-Vアドレスは01〜DFで指定してください。")
    return addr


def connect_configured(controller, settings, advanced):
    """Shared by main connection and test. Failure leaves no usable session."""
    try:
        status = controller.connect(settings.get("com_port", "AUTO"), settings.get("cat_baud", "AUTO") if settings.get("ptt") == "CAT" else settings.get("civ_baud", "AUTO"))
        if status.connected and settings.get("auto_data_mode", True):
            if not controller.set_data_mode(advanced.get("data_mode", "LSB-D")):
                controller.disconnect()
                controller.status.message = "DATAモード切替を確認できません。機種対応・設定を確認し、手動切替の場合は自動切替をOFFにしてください。"
        if controller.cancel.is_set():
            controller.disconnect()
        return controller.status
    except Exception as exc:
        controller.disconnect()
        controller.status.message = f"接続失敗: {exc}"
        return controller.status
