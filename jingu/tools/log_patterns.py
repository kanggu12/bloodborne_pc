#!/usr/bin/env python3
"""Message kinds of bbport run logs side by side. Each line is reduced to a pattern (addresses,
numbers and probed file names replaced) and the patterns are counted per log; the run length is
the count of once-a-minute 'Memory:' reports. Patterns that only the last log has are marked NEW,
patterns that an earlier log has and the last one lacks are marked GONE.

  log_patterns.py LOG [LOG ...] [--per-hour] [--top N] [--grep REGEX]
"""
import argparse
import re
from collections import Counter
from pathlib import Path

SUBS = [
    (re.compile(r'^Mods: .*'), 'Mods: ...'),
    (re.compile(r'open\((/app0/[^/)]+/[^/)]+)/[^)]*\)'), r'open(\1/...)'),
    (re.compile(r'0x[0-9a-fA-F]+'), '0x#'),
    (re.compile(r'\b[0-9a-fA-F]*\d[0-9a-fA-F]*\b'), '#'),
]


def pattern(line):
    for rx, repl in SUBS:
        line = rx.sub(repl, line)
    return line


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('logs', nargs='+', type=Path)
    p.add_argument('--per-hour', action='store_true', help='rates per hour of play instead of counts')
    p.add_argument('--top', type=int, default=0, help='show only the N most frequent unmarked patterns')
    p.add_argument('--grep', type=re.compile, help='show only patterns matching this')
    a = p.parse_args()
    counts, minutes, lines = [], [], []
    for log in a.logs:
        c = Counter()
        # newline='\n': a game started from a shortcut (--play) writes CR CR LF
        with open(log, encoding='utf-8', errors='replace', newline='\n') as f:
            for line in f:
                c[pattern(line.rstrip('\r\n'))] += 1
        counts.append(c)
        minutes.append(sum(n for k, n in c.items() if k.startswith('Memory: VRAM')))
        lines.append(sum(c.values()))
    last, earlier = counts[-1], counts[:-1]
    rows = []
    for key in set().union(*counts):
        if a.grep and not a.grep.search(key):
            continue
        mark = ''
        if earlier and last[key] and not any(c[key] for c in earlier):
            mark = 'NEW'
        elif last[key] == 0:
            mark = 'GONE'
        rows.append((mark, key))
    order = {'NEW': 0, 'GONE': 1, '': 2}
    rows.sort(key=lambda r: (order[r[0]], -last[r[1]], -sum(c[r[1]] for c in counts), r[1]))
    if a.top:
        rows = [r for r in rows if r[0]] + [r for r in rows if not r[0]][:a.top]

    def cell(i, key):
        n = counts[i][key]
        if a.per_hour:
            return f'{n * 60 / minutes[i]:7.1f}' if minutes[i] else '      -'
        return f'{n:7d}'

    for i, log in enumerate(a.logs):
        print(f'[{i}] {log.name}: {lines[i]} lines, {minutes[i]} min, {len(counts[i])} patterns')
    print('      ' + ''.join(f'{f"[{i}]":>7s}' for i in range(len(a.logs))))
    for mark, key in rows:
        print(f'{mark:5s} ' + ''.join(cell(i, key) for i in range(len(a.logs))) + '  ' + key[:160])
    print(f'{len(rows)} patterns shown' + (' (per hour)' if a.per_hour else ''))


if __name__ == '__main__':
    main()
