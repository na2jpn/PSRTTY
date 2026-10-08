"""Shared receive-level colors and a conservative low-level notice gate."""
import math

GRAY = '#a59d92'
LIGHT_BLUE = '#73cbe8'
GREEN = '#38a05b'
YELLOW = '#eacb45'
RED = '#d84a48'
NOTICE_BLUE = '#087fad'


def level_percent(value):
    try:value = float(value)
    except (ValueError, TypeError):return 0.
    return min(100., max(0., value * 100.)) if math.isfinite(value) else 0.


def level_color(percent):
    if percent <= 5:return GRAY
    if percent < 30:return LIGHT_BLUE
    if percent < 80:return GREEN
    if percent < 90:return YELLOW
    return RED


class LowLevelNotice:
    """Require recent printable decoding and sustained low audio, not silence.

    Timing uses the caller's monotonic clock so tests never need real waits.
    """
    def __init__(self):self.reset()
    def reset(self):
        self.percent=0.;self.last_level=None;self.last_char=None;self.low_since=None
    def decoded(self, now):self.last_char=now
    def level(self, value, now):
        self.percent=level_percent(value);self.last_level=now
    def visible(self, now, receiving=True):
        eligible=(receiving and self.last_level is not None and now-self.last_level <= .75
                  and self.last_char is not None and now-self.last_char <= 2.
                  and 0 < self.percent < 30)
        if not eligible:self.low_since=None;return False
        if self.low_since is None:self.low_since=now
        return now-self.low_since >= 3.


LABELS = ('', 'Low', 'Good', 'High', 'Over!')
COLORS = (GRAY, LIGHT_BLUE, GREEN, YELLOW, RED)
TEXT_COLORS = (GRAY, '#087fad', '#287b44', '#9a7800', RED)


def level_band(percent):
    if percent <= 5:return 0
    if percent < 30:return 1
    if percent < 80:return 2
    if percent < 90:return 3
    return 4


class LevelDisplay:
    """Display-only envelope; no changes to audio samples or decoder gain.

    Fast rise (120 ms), slow fall (450 ms), 250 ms band confirmation.
    Red entry at 90% is immediate to avoid hiding brief excessive input.
    """
    def __init__(self):self.reset()
    def reset(self):
        self.percent=0.;self.band=0;self.last_time=None;self.pending=None;self.pending_since=None
    def update(self, value, now):
        target=level_percent(value)
        dt=.08 if self.last_time is None else max(0.,now-self.last_time)
        self.last_time=now
        tau=.12 if target > self.percent else .45
        self.percent += (target-self.percent)*(1.-math.exp(-dt/tau))
        if target >= 90:self.percent=max(self.percent,target)
        candidate=level_band(round(self.percent))
        if candidate == self.band:
            self.pending=None;self.pending_since=None
        elif candidate == 4:
            self.band=candidate;self.pending=None;self.pending_since=None
        elif candidate != self.pending:
            self.pending=candidate;self.pending_since=now
        elif now-self.pending_since >= .25:
            self.band=candidate;self.pending=None;self.pending_since=None
        return round(self.percent)
