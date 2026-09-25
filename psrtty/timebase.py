"""Display/transcript JST; ADIF timestamps and month buckets UTC."""
from datetime import datetime, timedelta, timezone
JST = timezone(timedelta(hours=9), 'JST')
UTC = timezone.utc

def in_zone(value, zone):
    """Naive explicit values belong to the requested zone, never the host zone."""
    return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)
