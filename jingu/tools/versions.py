#!/usr/bin/env python3
"""Date versions of this project's mods, patches and exe fixes: <year>.<month>.<day>, the day the
item's behaviour (bytes, code, text files) last changed, with .2, .3 for a second, third release
that day. A new name or a new description is no new version. Names show it as " v<version>"."""
import re
import time

PATTERN = r'\d{4}\.\d{2}\.\d{2}(?:\.\d+)?'


def key(version):
    """For ordering: 2026.10.24 -> (2026, 10, 24, 1), 2026.10.24.3 -> (2026, 10, 24, 3)."""
    if not re.fullmatch(PATTERN, version):
        raise ValueError(f'not a date version: {version!r}')
    parts = tuple(int(x) for x in version.split('.'))
    return parts + ((1,) if len(parts) == 3 else ())


def today():
    return time.strftime('%Y.%m.%d')


def next_version(used, day=None):
    """DAY (default today), or DAY.N past every version of that day in USED."""
    day = day or today()
    taken = [key(v)[3] for v in used if isinstance(v, str) and (v == day or v.startswith(day + '.'))]
    return day if not taken else f'{day}.{max(taken) + 1}'
