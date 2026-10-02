from __future__ import annotations


def expand_macro(template: str, values: dict[str, str]) -> str:
    # Single pass: user text containing braces is never expanded recursively.
    import re
    normalized = {key.upper(): str(value) for key, value in values.items()}
    result = re.sub(r"\{([A-Z0-9_]+)\}", lambda m: normalized.get(m[1], m[0]), template)
    return "\n".join(line for raw in result.splitlines() if (line := " ".join(raw.split())))


TEMPLATE_NAME = "JARL World Wide RTTYコンテスト"


def jarl_ww_template() -> list[dict[str, str]]:
    """Return independent editable values, retaining legacy completion metadata."""
    rows = [
        ("CQ", "CQ TEST {MYCALL} {MYCALL} K"),
        ("CALL", "{MYCALL} {MYCALL} {MYCALL}"),
        ("EXCHANGE", "{HISCALL} 599 {SENT} {SENT} DE {MYCALL} K"),
        ("TU 73", "R TU 73 DE {MYCALL}"),
        ("AGN", "AGN DE {MYCALL} K"),
        ("NR?", "{HISCALL} NR NR?"),
        ("TEST", "RRR DE {MYCALL} TEST"),
        ("KKK", "KKK"),
        ("FREE", ""),
    ]
    return [dict(key=f"F{i+1}", name=name, text=text, completes_qso=(i == 3)) for i, (name, text) in enumerate(rows)]


NORMAL_TEMPLATE_NAME = "通常交信（英文RTTY）"


def normal_qso_template() -> list[dict[str, str]]:
    rows = [
        ("CQ", "CQ CQ DE {MYCALL} {MYCALL} K"),
        ("CALL", "{HISCALL} DE {MYCALL} {MYCALL} K"),
        ("RST", "{HISCALL} DE {MYCALL} TNX FER CALL UR RST {RSTS} {RSTS} K"),
        ("TU 73", "TU 73 {HISCALL} DE {MYCALL} SK"),
        ("RRR", "RRR TNX FER INFO {HISCALL} DE {MYCALL} K"),
        ("AGN", "PSE AGN AGN {HISCALL} DE {MYCALL} K"),
        ("QTH / INFO", "QTH {MYQTH} {MYJCCJCG}\n{MYTXT}\n{HISCALL} DE {MYCALL} K"),
        ("KKK", "KKK"),
        ("FREE", ""),
    ]
    return [dict(key=f"F{i+1}", name=name, text=text, completes_qso=(i == 3)) for i, (name, text) in enumerate(rows)]


CQWW_TEMPLATE_NAME = "CQ WW RTTY DXコンテスト"


def cqww_rtty_template() -> list[dict[str, str]]:
    # Same operating sequence; SENT carries the CQ zone instead of age.
    return jarl_ww_template()


SHORT_TEMPLATE_NAME = "通常交信短縮版（英文RTTY）"


def short_qso_template():
    texts = ["CQ DE {MYCALL} K", "{HISCALL} DE {MYCALL} K",
             "{HISCALL} DE {MYCALL} UR {RSTS} K", "TU 73 {HISCALL} SK",
             "RRR TU {HISCALL} DE {MYCALL} K", "AGN AGN",
             "MY QTH {MYJCCJCG} K", "KKK", ""]
    rows = normal_qso_template()
    for row, text in zip(rows, texts): row['text'] = text
    return rows


TEMPLATES = {NORMAL_TEMPLATE_NAME: normal_qso_template, SHORT_TEMPLATE_NAME: short_qso_template, TEMPLATE_NAME: jarl_ww_template,
             CQWW_TEMPLATE_NAME: cqww_rtty_template}

TEMPLATE_HELP = {
    NORMAL_TEMPLATE_NAME: "通常交信用の英文マクロです。自局情報は基本設定で入力してください。\n"
                          "テンプレートを選択して［反映］すると、F1～F9が置き換わります。反映後も自由に編集できます。",
    TEMPLATE_NAME: "コンテストナンバーは「RST＋年齢（または01）」です。\n"
                   "SENTにコンテスト開始時の年齢、または「01」を入力し、「固定」をONにしてください。\n"
                   "マルチオペで年齢を送る場合は、オペレータの平均年齢です。00・99も使用できます。\n"
                   "RST（599）はマクロで付くため、SENTへの入力は不要です。",
    CQWW_TEMPLATE_NAME: "コンテストナンバーは「RST＋CQゾーン番号」です。\n"
                        "実際の運用地のCQ Zoneを確認し、送信番号に設定してください。日本は25です。\n"
                        "「固定」をONにしてください。RST（599）はマクロで付くため、SENTへの入力は不要です。\n"
                        "米国本土・カナダ局の受信番号は州・地域略号も含めてRCVDに記録します（例：05 MA）。",
}


TEMPLATE_HELP[SHORT_TEMPLATE_NAME] = TEMPLATE_HELP[NORMAL_TEMPLATE_NAME]


def completes_qso(text: str) -> bool:
    import re
    return bool(re.search(r"(?<![A-Z0-9])TU\s+73(?![A-Z0-9])", text.upper()))
