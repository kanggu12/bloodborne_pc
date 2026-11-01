#!/usr/bin/env python3
"""Which eboot patches touch the same bytes, in a bbport install. A diagnostic listing only: the
overlap, survival and red zone verdicts come from the write model in launch_model.py, which also counts the built-in code patches (Quit to Desktop, Rebirth,
resolution) that this script does not see, and the launcher's Windows file order.

Reads the built-in patch file (patches/Bloodborne.xml) and the external ones
(Game/dvdroot_ps4/patches/*.xml), works out which entries the last run applied, and prints
  - every entry, selected or not, that overlaps an entry of the file named by --mine
  - every pair of selected entries that writes the same bytes with different values
    (bbport applies built-in patches first, then external files by name; the later write wins)
  - in that order, every selected entry whose bytes a later one overwrites, and any external
    entry that overlaps the built-in FPS preset (bbport then drops the whole preset)

Selection:
  external: patches.json {"enabled": [...], "disabled": [...]} "<file>/<name>" over isEnabled,
            the rule of scripts/patches.py external_selection()
  built-in: the names on the last run's "Patches: FPS preset ...; N writes from [...]" log line

  patch_audit.py INSTALL_DIR [--mine Bloodborne_fixes.xml] [--patches-config FILE] [--list]

--patches-config audits another selection than INSTALL_DIR/patches.json (a planned change);
--list prints every selected entry in bbport's order with how many of its bytes survive.
"""
import argparse
import ast
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SIZES = {'bytes16': 2, 'bytes32': 4, 'float32': 4, 'bytes64': 8, 'float64': 8}
FPS_NAMES = {'60 FPS++', '90 FPS++', 'Uncap FPS++'}   # scripts/patches.py FPS_PRESETS


def entries(path, origin):
    out = []
    root = ET.parse(path).getroot()
    for meta in root.iter('Metadata'):
        lines = []
        for line in meta.iter('Line'):
            kind, addr, value = line.get('Type'), line.get('Address'), line.get('Value', '')
            if not addr:
                continue
            if kind == 'bytes':
                data = bytes.fromhex(value)
            elif kind in ('bytes16', 'bytes32', 'bytes64'):
                data = int(value, 0).to_bytes(SIZES[kind], 'little')
            elif kind in ('float32', 'float64'):
                import struct
                data = struct.pack('<f' if kind == 'float32' else '<d', float(value))
            else:
                data = None
            lines.append((int(addr, 0), data if data is not None else b'?' * SIZES.get(kind, 1), kind))
        out.append({'origin': origin, 'file': path.name, 'name': meta.get('Name'),
                    'enabled_default': (meta.get('isEnabled') or 'false').lower() == 'true',
                    'app': meta.get('AppVer'), 'lines': lines})
    return out


def last_builtin_names(log):
    for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.search(r'Patches: FPS preset .*? writes from (\[.*\])', line)
        if m:
            return list(ast.literal_eval(m.group(1)))
    return []


def overlap(a, b):
    hits = []
    for addr_a, data_a, _ in a['lines']:
        for addr_b, data_b, _ in b['lines']:
            lo, hi = max(addr_a, addr_b), min(addr_a + len(data_a), addr_b + len(data_b))
            if lo < hi:
                same = data_a[lo - addr_a:hi - addr_a] == data_b[lo - addr_b:hi - addr_b]
                hits.append((lo, hi, same))
    return hits


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('install', type=Path)
    p.add_argument('--mine', default='Bloodborne_fixes.xml')
    p.add_argument('--patches-config', type=Path, help='default: INSTALL_DIR/patches.json')
    p.add_argument('--list', action='store_true', help='every selected entry, in order, with surviving bytes')
    a = p.parse_args()
    builtin = entries(a.install / 'patches' / 'Bloodborne.xml', 'built-in')
    external = []
    ext_dir = a.install / 'Game' / 'dvdroot_ps4' / 'patches'
    for f in sorted(ext_dir.glob('*.xml')):
        external += entries(f, 'external')
    cfg = json.loads((a.patches_config or a.install / 'patches.json').read_text(encoding='utf-8'))
    enabled, disabled = set(cfg.get('enabled', [])), set(cfg.get('disabled', []))
    for e in external:
        key = f'{e["file"]}/{e["name"]}'
        e['selected'] = key in enabled or (key not in disabled and e['enabled_default'])
    names = last_builtin_names(a.install / 'user' / 'last_run.log')
    for e in builtin:
        e['selected'] = e['name'] in names
    every = builtin + external
    selected = [e for e in every if e['selected'] and e['app'] in (None, '01.09')]
    print(f'entries: built-in {len(builtin)}, external {len(external)}; selected {len(selected)} '
          f'(built-in from the last run: {len([e for e in builtin if e["selected"]])} of {len(names)} names found)')
    mine = [e for e in external if e['file'] == a.mine]
    print(f'\n{a.mine}: {len(mine)} entries')
    for m in mine:
        others = [(o, overlap(m, o)) for o in every if o is not m]
        others = [(o, h) for o, h in others if h]
        state = 'selected' if m['selected'] else 'not selected'
        print(f'  [{state}] {m["name"]}: {len(m["lines"])} writes, overlaps {len(others)} other entries')
        for o, hits in others:
            tag = 'SELECTED' if o['selected'] else 'not selected'
            same = all(s for _, _, s in hits)
            print(f'      {tag:12s} {o["origin"]} {o["file"]}/{o["name"]}: '
                  f'{", ".join(f"{lo:#x}" for lo, hi, s in hits[:4])}'
                  f'{" (same bytes)" if same else " (different bytes)"}')
    print('\nselected entries writing the same bytes with different values:')
    found = 0
    for i, x in enumerate(selected):
        for y in selected[i + 1:]:
            hits = [h for h in overlap(x, y) if not h[2]]
            if hits:
                found += 1
                print(f'  {x["origin"]} {x["file"]}/{x["name"]}  <->  {y["origin"]} {y["file"]}/{y["name"]}: '
                      f'{len(hits)} ranges, first at {hits[0][0]:#x}')
    print(f'  {found} pairs')
    # bbport's order: built-in names as the log lists them, then external files by name
    order = [e for n in names for e in builtin if e['name'] == n and e['selected']]
    order += [e for e in external if e['selected'] and e['app'] in (None, '01.09')]
    final = {}   # address -> (last writer, byte)
    for e in order:
        for addr, data, _ in e['lines']:
            for i in range(len(data)):
                final[addr + i] = (e, data[i])
    print('\nselected entries left with bytes that differ from what they wrote (bbport order):')
    lost = 0
    for e in order:
        total = sum(len(d) for _, d, _ in e['lines'])
        over, same = {}, 0
        for addr, data, _ in e['lines']:
            for i in range(len(data)):
                w, b = final[addr + i]
                if w is e:
                    continue
                if b == data[i]:
                    same += 1
                else:
                    over.setdefault(id(w), [w, 0])[1] += 1
        if over:
            lost += 1
            by = '; '.join(f'{w["file"]}/{w["name"]} ({n})' for w, n in over.values())
            print(f'  {e["origin"]} {e["file"]}/{e["name"]}: {sum(n for _, n in over.values())} of {total} '
                  f'bytes, by {by}')
        elif same:
            print(f'  (same value) {e["origin"]} {e["file"]}/{e["name"]}: {same} of {total} bytes rewritten '
                  f'later with the same value')
    print(f'  {lost} entries')
    fps = [e for e in order if e['origin'] == 'built-in' and e['name'] in FPS_NAMES]
    clash = [(x['name'], y['name']) for x in order if x['origin'] == 'external' for y in fps if overlap(x, y)]
    print(f'external entries overlapping the built-in FPS preset {[e["name"] for e in fps]}: {len(clash)} {clash}')
    if a.list:
        print('\nselected entries in bbport order (bytes that end up as the entry wrote them):')
        for e in order:
            total = sum(len(d) for _, d, _ in e['lines'])
            kept = sum(final[addr + i][1] == data[i] for addr, data, _ in e['lines'] for i in range(len(data)))
            print(f'  {e["origin"]:8s} {e["file"]}/{e["name"]}: {kept} of {total}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
