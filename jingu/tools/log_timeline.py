#!/usr/bin/env python3
"""Timeline of a bbport last_run.log: notable events with the minute index (count of the
once-a-minute 'Memory:' reports seen so far), repeated lines collapsed into one row.

  log_timeline.py LOG"""
import re
import sys
from collections import Counter

RULES = [
    ('area_load', re.compile(r"guest thread 'CSChrThread0' created")),
    ('title_menu', re.compile(r"menu/\.gfx\) -> not found")),
    ('pm4_drop', re.compile(r'rest of the buffer dropped')),
    ('nextpacket', re.compile(r'NextPacket: .*exceeds')),
    ('find_range', re.compile(r'FindImageFromRange')),
    ('overlap', re.compile(r'Image overlap resolve failed')),
    ('stall', re.compile(r'^== Stall during rendering')),
    ('spirv', re.compile(r'emit_spirv')),
    ('copy_layers', re.compile(r'SanitizeCopyLayers')),
    ('srt_walker', re.compile(r'SrtWalkerSignalHandler')),
    ('null_vb', re.compile(r'vertex buffer table pointer is null')),
    ('trophy', re.compile(r'Runtime: trophy \d+ unlocked')),
    ('quit', re.compile(r'Quit to Desktop$')),
    ('fault', re.compile(r'Fault|STOP|Panic|assert|Assertion|Device lost|DeviceLost|UNREACHABLE', re.I)),
    ('upscaler', re.compile(r'^(Upscaler|DLSS|FSR|Output resolution|Settings)')),
    ('missing_map', re.compile(r'open\(/app0/dvdroot_ps4/map/.*not found')),
]
if len(sys.argv) != 2 or sys.argv[1].startswith('-'):
    sys.exit(__doc__)
minute, rows, counts = 0, [], Counter()
mem = []
# newline='\n': a game started from a shortcut (--play) writes CR CR LF; line numbers match grep -n
for n, line in enumerate(open(sys.argv[1], encoding='utf-8', errors='replace', newline='\n'), 1):
    line = line.rstrip('\r\n')
    if line.startswith('Memory: VRAM'):
        minute += 1
        m = re.search(r'VRAM (\d+) MiB; textures (\d+).*process (\d+) MiB committed, (\d+) MiB in RAM', line)
        if m:  # another build may word the report differently: the minute still counts
            mem.append((minute, n, *map(int, m.groups())))
        continue
    for kind, rx in RULES:
        if rx.search(line):
            counts[kind] += 1
            text = re.sub(r'^GPU \[[^]]+\] <\w+> ', '', line)[:120]
            if rows and rows[-1][2] == kind and (kind in ('find_range', 'srt_walker', 'title_menu', 'quit', 'missing_map') or rows[-1][3] == text):
                rows[-1][4] += 1
            else:
                rows.append([minute, n, kind, text, 1])
            break
skip = {'missing_map'}
for minute_, n, kind, text, rep in rows:
    if kind in skip:
        continue
    print(f'min {minute_:3d}  line {n:6d}  {kind:12s} x{rep:<5d} {text}')
print('\ncounts:', dict(counts))
print(f'memory reports: {len(mem)}')
sample = mem[:: max(1, len(mem) // 12)]
for m in sample + [x for x in mem[-1:] if x not in sample]:
    print(f'  min {m[0]:3d} line {m[1]:6d}  VRAM {m[2]} MiB  textures {m[3]}  process {m[4]} MiB committed, {m[5]} MiB RAM')
