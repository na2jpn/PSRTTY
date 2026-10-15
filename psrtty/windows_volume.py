"""Windows Core Audio controls, bound to the selected endpoint and our PID.

No lookup by friendly name, no fallback to the default endpoint, no writes on
read. Imports stay lazy so non-Windows builds keep working.
"""
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class VolumeState:
    percent: int
    muted: bool


class VolumeUnavailable(RuntimeError):
    def __init__(self, reason, detail=''):
        super().__init__(detail or reason)
        self.reason = reason


def volume_error(exc, default='read'):
    if isinstance(exc, VolumeUnavailable):
        return exc
    value = getattr(exc, 'hresult', None)
    if value is None and exc.args and isinstance(exc.args[0], int):
        value = exc.args[0]
    reason = {0x88890001: 'not_ready', 0x88890004: 'device',
              0x88890010: 'service', 0x88890026: 'device'}.get(
                  (value & 0xffffffff) if isinstance(value, int) else 0, default)
    return VolumeUnavailable(reason, str(exc))


class WindowsVolume:
    def __init__(self, selection, kind):
        if sys.platform != 'win32':
            raise VolumeUnavailable('platform')
        try:
            import comtypes
            from pycaw.pycaw import (AudioUtilities, IAudioEndpointVolume,
                                      IAudioSessionManager2, IAudioSessionControl2,
                                      ISimpleAudioVolume)
        except ImportError as exc:
            raise VolumeUnavailable('dependency', str(exc)) from exc
        from .audio_engine import sd
        from .audio_devices import resolve_device, wasapi_endpoint
        if selection == 'UNSET':
            raise VolumeUnavailable('selection')
        try:
            index = resolve_device(sd, selection, kind)
            endpoint_id, active = wasapi_endpoint(sd, index)
        except Exception as exc:
            raise VolumeUnavailable('device', str(exc)) from exc
        if not active:
            raise VolumeUnavailable('device')
        try:
            device = AudioUtilities.GetDeviceEnumerator().GetDevice(endpoint_id)
        except Exception as exc:
            raise volume_error(exc, 'device') from exc
        self.device = device
        self.kind = kind
        self._interfaces = (IAudioSessionControl2, ISimpleAudioVolume)
        self._empty_volume = None
        interface = IAudioEndpointVolume if kind == 'input' else IAudioSessionManager2
        try:
            self.control = device.Activate(interface._iid_, comtypes.CLSCTX_ALL, None).QueryInterface(interface)
        except Exception as exc:
            raise volume_error(exc) from exc

    def _sessions(self):
        ctl_type, volume_type = self._interfaces
        enumerator = self.control.GetSessionEnumerator()
        volumes = []
        for index in range(enumerator.GetCount()):
            session = enumerator.GetSession(index).QueryInterface(ctl_type)
            if session.GetProcessId() == os.getpid() and session.GetState() != 2:
                volumes.append(session.QueryInterface(volume_type))
        if not volumes:
            # Microsoft: GUID_NULL + cross-process FALSE opens an empty session
            # for this process on THIS endpoint. PortAudio's shared WASAPI output
            # uses the same default session. No audio client/stream or PTT is used.
            # Keep the COM interface alive while the settings widget owns us.
            if self._empty_volume is None:
                try:
                    self._empty_volume = self.control.GetSimpleAudioVolume(None, 0)
                except Exception as exc:
                    raise volume_error(exc, 'not_ready') from exc
            volumes.append(self._empty_volume)
        return volumes

    def read(self):
        if self.kind == 'input':
            return VolumeState(round(self.control.GetMasterVolumeLevelScalar()*100), bool(self.control.GetMute()))
        states = [VolumeState(round(v.GetMasterVolume()*100), bool(v.GetMute())) for v in self._sessions()]
        if any(state != states[0] for state in states):
            raise VolumeUnavailable('mixed')
        return states[0]

    def set_percent(self, percent):
        value = max(0, min(100, int(percent))) / 100
        if self.kind == 'input':
            self.control.SetMasterVolumeLevelScalar(value, None)
        else:
            for volume in self._sessions():
                volume.SetMasterVolume(value, None)

    def set_mute(self, muted):
        controls = [self.control] if self.kind == 'input' else self._sessions()
        for volume in controls:
            volume.SetMute(bool(muted), None)
