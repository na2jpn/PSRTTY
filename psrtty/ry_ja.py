"""JA terrestrial RTTY display filter; JARL band plan effective 2025-07-17.
Not a transmitter interlock or a licence/occupied-bandwidth determination.
Special satellite/EME-only sections and repeater/beacon channels are excluded.
Source: https://www.jarl.org/Japanese/A_Shiryo/A-3_Band_Plan/bandplan20250717.pdf
Intervals are half open. A listed beacon carrier is excluded explicitly.
"""
JA_RTTY_MHZ = ((1.830,1.875),(1.9075,1.9125),
 (3.530,3.580),(3.599,3.612),(3.662,3.687),(3.702,3.716),(3.745,3.770),(3.791,3.805),
 (7.030,7.200),(10.120,10.150),(14.070,14.350),(18.080,18.168),
 (21.070,21.450),(24.900,24.990),(28.070,29.300),(29.510,29.590),
 (50.070,54.000),(144.100,144.500),(145.650,145.800),
 (430.100,430.700),(439.000,440.000),
 (1293.000,1294.500),(1294.600,1295.800),(1296.200,1299.000))
JA_RTTY_HZ = tuple((round(lo*1e6),round(hi*1e6)) for lo,hi in JA_RTTY_MHZ)
BEACONS = frozenset((14100000,18110000,21150000,24930000,28200000))


def ja_rtty(hz):
    return hz is not None and hz not in BEACONS and any(lo <= hz < hi for lo,hi in JA_RTTY_HZ)


def ja_band(band):
    from .ry_spots import band_for
    return any(band_for(lo)==band for lo,hi in JA_RTTY_HZ)


def ja_pair(mark,mark_high=True):
    # Check both RF tones, including any boundary/beacon between them.
    space=mark-170 if mark_high else mark+170
    lo,hi=sorted((mark,space))
    return any(a<=lo and hi<b for a,b in JA_RTTY_HZ) and not any(lo<=b<=hi for b in BEACONS)
