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
    "IC-7851": 0x8E,
    "IC-7200": 0x76,
    "IC-7410": 0x80,
    "IC-7600": 0x7A,
    "IC-9100": 0x7C,
    "その他ICOM": 0x00,
}

from .macros import normal_qso_template

DEFAULT_MACROS = normal_qso_template()

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "0.84",
    "schema_version": 1,
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
    "qso": {"sent": "001", "sent_fixed": True},
    "auto_cq": {"count": 10, "interval_seconds": 7},
    "audio": {
        "input_device": "UNSET",
        "output_device": "AUTO",
        "rx_gain": 1.0,
        "tx_gain": 0.35,
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
        "latest_qso_count": 4,
        "decode_sq": 4,
        "wheel_reverse": False,
        "spectrum_gain_db": 0,
        "rx_card_font_size": 12,
        "auto_get_call": True,
        "auto_log": False,
    },
}


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

    def load(self) -> None:
        previous_font = None
        if self.config_path.exists():
            try:
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.data = _merge(DEFAULT_CONFIG, raw)
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

        ui = self.data['ui']
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
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.macro_path.write_text(
            json.dumps(self.macros, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def reset_advanced(self) -> None:
        self.data["advanced"] = deepcopy(DEFAULT_CONFIG["advanced"])
