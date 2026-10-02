"""Display/transcript JST; ADIF timestamps and month buckets UTC."""
from datetime import datetime, timedelta, timezone
JST = timezone(timedelta(hours=9), 'JST')
UTC = timezone.utc

def in_zone(value, zone):
    """Naive explicit values belong to the requested zone, never the host zone."""
    return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)


def display_zone(name='JST'):
    return UTC if name == 'UTC' else JST


def zone_name(parent=None):
    """Resolve the current display preference without changing stored timestamps."""
    while parent is not None:
        if hasattr(parent, 'store'):
            return 'UTC' if parent.store.data.get('ui', {}).get('time_zone') == 'UTC' else 'JST'
        parent = parent.parent() if hasattr(parent,'parent') else None
    return 'JST'
