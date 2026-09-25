def frequency_text(hz):
    if not hz:
        return "---.---.--- MHz"
    mhz, rest = divmod(int(hz), 1000000)
    khz, hz = divmod(rest, 1000)
    return f"{mhz}.{khz:03d}.{hz:03d} MHz"


def band_text(qso):
    names = {"2190m":"0.135", "630m":"0.472", "160m":"1.8", "80m":"3.5",
             "40m":"7", "30m":"10", "20m":"14", "17m":"18", "15m":"21",
             "12m":"24", "10m":"28", "6m":"50", "2m":"144", "70cm":"430",
             "23cm":"1200", "13cm":"2400", "6cm":"5600", "3cm":"10000"}
    band = qso.band
    return f"{band} / {names[band]}MHz" if band in names else band
