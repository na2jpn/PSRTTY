from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .paths import ensure_runtime_dirs


RIG_MODELS: dict[str, int] = {
    "IC-705": 0xA4,
    "IC-7300": 0x94,
    "IC-7300MK2": 0xB6,
    "IC-905": 0xAC,
    "IC-7100": 0x88,
    "IC-9700": 0xA2,
    "IC-7610": 0x98,
    "IC-7760": 0xB2,
    "IC-7851": 0x8E,
    "IC-7200": 0x76,
    "IC-7410": 0x80,
    "IC-7600": 0x7A,
    "IC-9100": 0x7C,
    'IC-756PRO': 0x5C,
    'IC-756PROII': 0x64,
    'IC-756PROIII': 0x6E,
    'IC-703': 0x68,
    'IC-7000': 0x70,
    'IC-746': 0x56,
    'IC-7400 / IC-746PRO': 0x66,
    'IC-7700': 0x74,
    'IC-7800': 0x6A,
    'IC-910 / IC-910H': 0x60,
    'IC-706': 0x48,
    'IC-706MkII': 0x4E,
    'IC-706MkIIG': 0x58,
    'IC-707': 0x3E,
    'IC-78': 0x62,
    'IC-718': 0x5E,
    'IC-725': 0x28,
    'IC-726': 0x30,
    'IC-728': 0x38,
    'IC-729': 0x3A,
    'IC-735': 0x04,
    'IC-736': 0x40,
    'IC-737': 0x3C,
    'IC-738': 0x44,
    'IC-756': 0x50,
    'IC-761': 0x1E,
    'IC-765': 0x2C,
    'IC-775': 0x46,
    'IC-781': 0x26,
    'IC-271': 0x20,
    'IC-275': 0x10,
    'IC-375': 0x12,
    'IC-471': 0x22,
    'IC-475': 0x14,
    'IC-575': 0x16,
    'IC-820H': 0x42,
    'IC-821H': 0x4C,
    'IC-970': 0x2E,
    'IC-1275': 0x18,
    "その他ICOM": 0x00,
}

from .macros import normal_qso_template

DEFAULT_MACROS = normal_qso_template()

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1.12",
    "schema_version": 1,
    "hamlog": {"enabled": False, "auto_save": False},
    "backup": {"on_exit": True, "every_enabled": False, "every_count": 30, "pending_qsos": 0},
    "station_callsign": "",
    "station": {"qth": "", "jcc_jcg": "", "text": ""},
    "radio": {
        "model": "",
        "civ_address": "",
        "auto_data_mode": True,
        "com_port": "AUTO",
        "civ_baud": "AUTO",
        "ptt": "CI-V",
    },
    "external": {
        "role": "prekey",
        "enabled": False,
        "com_port": "",
        "line": "RTS",
        "reversed": False,
        "delay_seconds": 0.1,
    },
    "qso": {"sent": "001", "sent_fixed": True},
    "auto_cq": {"count": 10, "interval_seconds": 7},
    "audio": {
        "input_device": "UNSET",
        "output_device": "AUTO",
        "rx_gain": 0.5,
        "tx_gain": 0.35,
        "secondary": {"enabled": False, "device": "UNSET", "gain": 1.0},
        "sample_rate": 48000,
    },
    "advanced": {
        "data_mode": "LSB-D",
        "rtty_baud": 45.45,
        "shift_hz": 170,
        "mark_hz": 2125,
        "space_hz": 2295,
        "invert": False,
        "spectrum_width_hz": 1000,
        "auto_tune_tolerance_hz": 90,
    },
    "ui": {
        "language": "ja",
        "time_zone": "JST",
        "latest_qso_count": 4,
        "decode_sq": 4,
        "decode_ignore_chars": 0,
        "wheel_reverse": False,
        "spectrum_gain_db": 0,
        "rx_card_font_size": 12,
        "auto_get_call": True,
        "cq_only": True,
        "clear_on_frequency": True,
        "auto_log": False,
    },
}

PROFILE_KEYS = ("station_callsign", "station", "radio", "external", "audio", "advanced")
from .printer import DEFAULT_PRINTER, normalize_settings
DEFAULT_CONFIG['printer'] = deepcopy(DEFAULT_PRINTER)
DEFAULT_CONFIG['active_profile'] = 0
DEFAULT_CONFIG['profiles'] = [{"name": "Profile1", **{
    key: deepcopy(DEFAULT_CONFIG[key]) for key in PROFILE_KEYS}}]


def profile_name(value: Any) -> str:
    name = str(value or "")
    return name if 1 <= len(name) <= 10 and name.isascii() and all(c.isalnum() or c in '-/' for c in name) else ""


def _merge(default: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(default)
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class ConfigStore:
    def __init__(self, config_path: Path | None = None, macro_path: Path | None = None):
        paths = ensure_runtime_dirs()
        self.config_path = config_path or (paths["config"] / "psrtty.json")
        self.macro_path = macro_path or (paths["config"] / "macros.json")
        self.data = deepcopy(DEFAULT_CONFIG)
        self.macros = deepcopy(DEFAULT_MACROS)
        self.load()

    def _profile_values(self) -> dict[str, Any]:
        return {**{key: deepcopy(self.data[key]) for key in PROFILE_KEYS},
                "rx_tones": deepcopy(self.data["ui"].get("rx_tones"))}

    def _load_profiles(self, raw_profiles=None) -> None:
        profiles = []
        if isinstance(raw_profiles, list):
            for item in raw_profiles[:8]:
                if not isinstance(item, dict):
                    continue
                values = {key: _merge(DEFAULT_CONFIG[key], item.get(key, {}))
                          if isinstance(DEFAULT_CONFIG[key], dict) and isinstance(item.get(key), dict)
                          else deepcopy(item.get(key, DEFAULT_CONFIG[key])) for key in PROFILE_KEYS}
                values["name"] = profile_name(item.get("name")) or f"Profile{len(profiles)+1}"
                tones = item.get("rx_tones")
                values["rx_tones"] = deepcopy(tones) if isinstance(tones, list) and len(tones) == 2 else None
                profiles.append(values)
        if not profiles:
            profiles = [{**self._profile_values(), "name": "Profile1"}]
        self.data["profiles"] = profiles
        index = self.data.get("active_profile", 0)
        self.data["active_profile"] = index if isinstance(index, int) and 0 <= index < len(profiles) else 0
        active = self.data["active_profile"]
        if isinstance(raw_profiles, list) and active < len(raw_profiles) and isinstance(raw_profiles[active], dict):
            if "rx_tones" not in raw_profiles[active]:
                profiles[active]["rx_tones"] = deepcopy(self.data["ui"].get("rx_tones"))
        for key in PROFILE_KEYS:
            self.data[key] = deepcopy(profiles[self.data["active_profile"]][key])
        tones = profiles[self.data["active_profile"]].get("rx_tones")
        if tones is None: self.data["ui"].pop("rx_tones", None)
        else: self.data["ui"]["rx_tones"] = deepcopy(tones)

    def snapshot_profile(self) -> None:
        item = self.data["profiles"][self.data["active_profile"]]
        item.update(self._profile_values())

    def activate_profile(self, index: int) -> None:
        if not 0 <= index < len(self.data["profiles"]):
            raise IndexError(index)
        self.snapshot_profile()
        self.data["active_profile"] = index
        for key in PROFILE_KEYS:
            self.data[key] = deepcopy(self.data["profiles"][index][key])
        tones = self.data["profiles"][index].get("rx_tones")
        if tones is None: self.data["ui"].pop("rx_tones", None)
        else: self.data["ui"]["rx_tones"] = deepcopy(tones)
        self.save()

    def load(self) -> None:
        previous_font = None
        profile_records = None
        if self.config_path.exists():
            try:
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.data = _merge(DEFAULT_CONFIG, raw)
                    profile_records = raw.get('profiles')
                    previous_font = raw.get("ui", {}).get("rx_card_font_size")
            except Exception:
                self.data = deepcopy(DEFAULT_CONFIG)
        if self.macro_path.exists():
            try:
                raw = json.loads(self.macro_path.read_text(encoding="utf-8"))
                if isinstance(raw, list) and len(raw) in (8, 9):
                    if all(isinstance(m, dict) and all(isinstance(m.get(k), str) for k in ("name", "text")) for m in raw):
                        self.macros = deepcopy(DEFAULT_MACROS)
                        for i, m in enumerate(raw):
                            self.macros[i] = dict(m, key=f"F{i+1}")
            except Exception:
                self.macros = deepcopy(DEFAULT_MACROS)

        self._load_profiles(profile_records)
        from .secondary_audio import normalize_settings as normalize_secondary
        for profile in self.data['profiles']:
            profile['audio']['secondary'] = normalize_secondary(profile['audio'].get('secondary'))
        self.data['audio']['secondary'] = deepcopy(self.data['profiles'][self.data['active_profile']]['audio']['secondary'])

        hamlog = self.data.get('hamlog')
        if not isinstance(hamlog, dict): hamlog = {}
        self.data['hamlog'] = {key: hamlog.get(key) is True for key in ('enabled', 'auto_save')}
        self.data['printer'] = normalize_settings(self.data.get('printer'))
        ui = self.data['ui']
        try: ui['decode_ignore_chars'] = max(0, min(10, int(ui.get('decode_ignore_chars', 0))))
        except (TypeError, ValueError, OverflowError): ui['decode_ignore_chars'] = 0
        if ui.get('time_zone') not in ('JST', 'UTC'): ui['time_zone'] = 'JST'
        if ui.get('language') not in ('ja', 'en', 'ru', 'zh', 'ko', 'id', 'th', 'es'):
            ui['language'] = 'ja'
        if ui.get('latest_qso_count') not in (2, 4, 6, 8, 10):
            ui['latest_qso_count'] = 4
        if not ui.get('compact_font_v40'):
            # Shrink existing choices once; fresh installations already use 12 pt.
            if isinstance(previous_font, (int, float)):
                ui['rx_card_font_size'] = max(10, int(previous_font) - 2)
            ui['compact_font_v40'] = True
        self.data['version'] = DEFAULT_CONFIG['version']
        # One-time migration of the untouched old F8 only. Keep custom macros.
        if not self.data.get("macro_defaults_v03"):
            if self.macros[7].get("name") == "FREE" and not self.macros[7].get("text"):
                self.macros[7] = deepcopy(DEFAULT_MACROS[7])
            self.data["macro_defaults_v03"] = True

    def save(self) -> None:
        self.snapshot_profile()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.macro_path.write_text(
            json.dumps(self.macros, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def reset_advanced(self) -> None:
        self.data["advanced"] = deepcopy(DEFAULT_CONFIG["advanced"])
