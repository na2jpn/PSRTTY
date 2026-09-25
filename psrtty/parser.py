from __future__ import annotations

import re
from dataclasses import dataclass

# Practical contest-oriented detector, intentionally conservative enough to
# avoid most exchange numbers. Explicit card selection still lets the user
# correct anything it misses.
CALL_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z0-9]{1,3}\d[A-Z]{1,4}(?:/[A-Z0-9]{1,5})?)(?![A-Z0-9])",
    re.IGNORECASE,
)
RST_RE = re.compile(r"(?<!\d)([1-5][1-9][1-9])(?!\d)")
TOKEN_RE = re.compile(r"[A-Z0-9][A-Z0-9/\-]{0,15}", re.IGNORECASE)


# CQ WW RTTY 2026 IV.C.3: continental US/DC and 14 Canadian call areas.
CQWW_QTH = frozenset("AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC NB NS QC ON MB SK AB BC NWT NF LB NU YT PEI".split())


@dataclass
class ParsedExchange:
    callsign: str = ""
    rst: str = ""
    exchange: str = ""


def normalize_call(value: str) -> str:
    return value.strip().upper().replace(" ", "")


def parse_exchange(text: str, mycall: str = "", *, cqww: bool = False) -> ParsedExchange:
    upper = text.upper()
    mycall = normalize_call(mycall)
    calls = [normalize_call(m.group(1)) for m in CALL_RE.finditer(upper)]
    calls = [c for c in calls if not mycall or c != mycall]
    call = calls[0] if calls else ""

    rst_match = RST_RE.search(upper)
    rst = rst_match.group(1) if rst_match else ""
    exchange = ""
    if rst_match:
        tail = upper[rst_match.end():]
        tokens = [t.strip("-/") for t in TOKEN_RE.findall(tail)]
        for index, token in enumerate(tokens):
            token = token.strip("-/")
            if not token or token == rst or token == call or token == mycall:
                continue
            if CALL_RE.fullmatch(token):
                continue
            exchange = token
            if cqww and token.isdigit() and len(token) <= 2 and 1 <= int(token) <= 40:
                # Only an adjacent official QTH, allowing repeated zone numbers.
                for following in tokens[index + 1:]:
                    if following == token:
                        continue
                    if following in CQWW_QTH:
                        exchange += " " + following
                    break
            break
    return ParsedExchange(call, rst, exchange)
