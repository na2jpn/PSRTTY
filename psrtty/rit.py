"""RIT protocol adapters. Reads never initialize or alter a radio setting."""
import ctypes

VFO = 1 << 29
RIT = 1 << 24


def _icom_query(self, sub):
    self.ser.reset_input_buffer(); self.ser.write(self._frame(0x21, sub))
    raw = self._read_response(0x21, timeout=.25)
    return raw[6:-1] if len(raw) >= 8 and raw[4:6] == bytes((0x21, sub)) else b''


def icom_read_rit(self):
    with self._lock:
        if type(self).__name__ != 'CIVController' or not self._control_ready(): return None
        raw = _icom_query(self, 0)
        if len(raw) != 3 or raw[2] not in (0, 1): return None
        from .civ import decode_bcd_frequency
        try: offset = decode_bcd_frequency(raw[:2]) * (-1 if raw[2] else 1)
        except ValueError: return None
        flag = _icom_query(self, 1)
        on = bool(flag[0]) if len(flag) == 1 and flag[0] in (0, 1) else None
        xit = _icom_query(self, 2)
        # Shared RIT/Delta-TX offset must not move the transmit frequency.
        blocked = xit == b'\x01'
        return dict(offset=offset, on=on, limit=9999, offset_write=not blocked,
                    on_write=on is not None, xit=blocked)


def icom_set_rit(self, *, offset=None, on=None):
    with self._lock:
        if not self._control_ready() or self.read_transmitting() is not False: return False
        state = icom_read_rit(self)
        if state is None: return False
        if offset is not None:
            if not state['offset_write'] or type(offset) is not int or abs(offset) > state['limit']: return False
            value=abs(offset)
            payload=((value%10)|((value//10%10)<<4), (value//100%10)|((value//1000%10)<<4), int(offset<0))
            sub=0
        elif on is not None:
            if not state['on_write']: return False
            sub=1; payload=(int(bool(on)),)
        else: return False
        self.ser.reset_input_buffer(); self.ser.write(self._frame(0x21, sub, *payload))
        if self._read_response(timeout=.25)[4:5] != b'\xfb': return False
        result=icom_read_rit(self)
        return bool(result and (result['offset']==offset if offset is not None else result['on'] is bool(on)))


def _hamlib_func(self, flag):
    get=getattr(self.lib,'rig_get_func',None)
    if get is None: return None
    value=ctypes.c_int()
    return bool(value.value) if get(self.handle,VFO,flag,ctypes.byref(value))==0 else None


def hamlib_read_rit(self):
    with self._lock:
        if not self._control_ready(): return None
        get=getattr(self.lib,'rig_get_rit',None)
        if get is None: return None
        value=ctypes.c_long()
        if get(self.handle,VFO,ctypes.byref(value))!=0: return None
        on=_hamlib_func(self,RIT)
        xit=None
        # Backends may share the physical RIT/XIT control. Inspect XIT via its
        # parsed flag rather than assuming a numeric value.
        parse=getattr(self.lib,'rig_parse_func',None)
        if parse:
            flag=parse(b'XIT')
            if flag: xit=_hamlib_func(self,flag)
        setter=getattr(self.lib,'rig_set_rit',None)
        has=getattr(self.lib,'rig_has_set_func',None)
        on_write=bool(on is not None and getattr(self.lib,'rig_set_func',None) and has and has(self.handle,RIT))
        # Conservative control span; backend validates its own step and limits.
        limit=9990 if self.model in ('FT-817 / FT-817ND','FT-818ND','FT-857 / FT-857D') else 9999
        return dict(offset=int(value.value),on=on,limit=limit,offset_write=bool(setter) and on_write and xit is not True,
                    on_write=on_write,xit=xit is True)


def hamlib_set_rit(self, *, offset=None, on=None):
    with self._lock:
        if not self._control_ready() or self.read_transmitting() is not False: return False
        state=hamlib_read_rit(self)
        if not state: return False
        if offset is not None:
            if not state['offset_write'] or type(offset) is not int or abs(offset)>state['limit']: return False
            # Hamlib documents that set_rit(0) can disable RIT. Preserve the
            # independently readable ON/OFF state when the backend supports it.
            if not state['on_write']: return False
            if self.lib.rig_set_rit(self.handle,VFO,offset)!=0:return False
            if self.lib.rig_set_func(self.handle,VFO,RIT,int(state['on']))!=0:return False
        elif on is not None:
            if not state['on_write'] or self.lib.rig_set_func(self.handle,VFO,RIT,int(bool(on)))!=0:return False
        else:return False
        result=hamlib_read_rit(self)
        return bool(result and (result['offset']==offset and result['on'] is state['on'] if offset is not None else result['on'] is bool(on)))
