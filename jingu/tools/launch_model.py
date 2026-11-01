#!/usr/bin/env python3
"""What the bbport launcher hands the game, rebuilt from the
launcher's settings.json and the install's own scripts, the way the launcher (game_environment,
saves_folder in launcher/bbport_launcher_win.py) and run.py do it on Windows.

- Environment: the launcher's own keys first (draw_pipe -> BB_DRAW_PIPE, ...), then every
  extra_env NAME=VALUE in order; the last one wins.
- Folders: patches_dir or <install>/patches, user_dir or <install>/user (saves, last_run.log),
  mods_dir or <install>/mods, game_dir or <install>/Game.
- External patch files as the launcher's Windows Python lists them (scripts/patches.py,
  external_patches): *.xml in any letter case, in case-insensitive order, without the built-in
  patches/Bloodborne.xml and bbbridge-live-map.xml. The install's patches.py run here under Linux
  rules lists them differently when names differ in case only; the write model reports that.
- Write model: the install's prepare.py and patches.py run into a temporary folder with the
  launcher's arguments; the final patches.bin is split into built-in and per-entry external writes
  for the overlap, survival and red zone verdicts. With minimal=True the game folder is reduced to
  eboot.bin, sce_sys and sce_module (prepare.py reads dvdroot_ps4 only to count its files), which
  takes seconds instead of minutes; update_check.py compares it with the full folder.
"""
import hashlib
import importlib.util
import json
import re
import shutil
import struct
import subprocess
import sys
import os
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The port's folder and the launcher's settings: BB_INSTALL and BB_SETTINGS. Without them, this checkout and %APPDATA%.
INSTALL = Path(os.environ.get('BB_INSTALL', HERE.parent.parent))
SETTINGS = Path(os.environ.get('BB_SETTINGS', Path(os.environ.get('APPDATA', '')) / 'bbport-launcher' / 'settings.json'))
OURS = HERE.parent / 'patches' / 'Bloodborne_fixes.xml'
OURS_BEFORE = ('Bloodborne_frame_heap.xml',)  # its name until 2026-10-24: a copy left under it applies twice
INTENDED = {frozenset({'Bloodborne_exit_game.xml/Exit Game (title menu)',
                       'Bloodborne_fixes.xml/Exit Fix: Exit Game (title menu) Closes Cleanly v2026.10.20'})}
LAUNCHER_KEYS = (('draw_pipe', 'BB_DRAW_PIPE'), ('readbacks', 'BB_READBACKS'), ('frames_ahead', 'BB_FRAMES_AHEAD'),
                 ('low_vram', 'BB_LOW_VRAM'))


def win_path(text):
    m = re.match(r'([A-Za-z]):[\\/](.*)', text or '')
    return Path(f'/mnt/{m.group(1).lower()}/' + m.group(2).replace('\\', '/')) if m else None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def patch_name(file_name):
    """0004-fix-rainbow-tiles-v2026.10.23.patch -> fix-rainbow-tiles-v2026.10.23"""
    return re.sub(r'^\d+-|\.patch$', '', file_name)


def read_settings(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'{path}: not a settings object')
    return data


def game_env(s):
    """The variables the launcher sets from these settings that the checks look at, extra_env last."""
    env = {name: str(s[key]) for key, name in LAUNCHER_KEYS if s.get(key)}
    for item in str(s.get('extra_env', '')).split():
        if '=' in item:
            name, value = item.split('=', 1)
            env[name] = value
    return env


def folders(s, install):
    return {'patches': win_path(s.get('patches_dir')) or install / 'patches',
            'user': win_path(s.get('user_dir')) or install / 'user',
            'mods': win_path(s.get('mods_dir')) or install / 'mods',
            'game': win_path(s.get('game_dir')) or install / 'Game'}


def install_module(install, name):
    """The install's scripts/NAME.py as a module, without writing __pycache__ into the install."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(f'bbport_install_{name}', install / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def xml_files(install, directory):
    """(Windows list, Linux list) of the external patch files patches.py reads from DIRECTORY."""
    if not directory.is_dir():
        return [], []
    builtin = (install / 'patches' / 'Bloodborne.xml').resolve()

    def keep(p):
        return p.is_file() and p.resolve() != builtin and p.name.lower() != 'bbbridge-live-map.xml'
    windows = sorted((p for p in directory.iterdir() if p.suffix.lower() == '.xml' and keep(p)),
                     key=lambda p: p.name.casefold())
    linux = [p for p in sorted(directory.glob('*.xml')) if keep(p)]
    return windows, linux


def external_entries(install, directory):
    """[(key, default_on, lines)] in the order the launcher's patches.py applies them on Windows."""
    patches = install_module(install, 'patches')
    ids = getattr(patches, 'BLOODBORNE_IDS', None)
    port_file = getattr(patches, 'port_patch_file', None)  # 1.9.5 on: a copy of the port's own file is not read
    out = []
    for path in xml_files(install, directory)[0]:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        if port_file and port_file(path, root):
            continue
        found = {e.text.strip() for e in root.iter('ID') if e.text}
        if ids and found and not found & set(ids):
            continue
        for meta in root.iter('Metadata'):
            if meta.get('AppVer') == '01.09' and meta.get('AppElf', 'eboot.bin') == 'eboot.bin':
                out.append((f'{path.name}/{meta.get("Name")}', (meta.get('isEnabled') or '').lower() == 'true',
                            len(list(meta.iter('Line')))))
    return out


def selected_entries(install, directory):
    """[(key, lines)] that patches.json selects, in the order they are applied."""
    cfg = json.loads((install / 'patches.json').read_text(encoding='utf-8'))
    enabled, disabled = set(cfg.get('enabled', [])), set(cfg.get('disabled', []))
    return [(k, n) for k, on, n in external_entries(install, directory) if k in enabled or (k not in disabled and on)]


def program_files(install):
    """(version, [program files that differ]) by the install's own check (scripts/package_files.py, 1.9.5 on:
    the launcher asks before every start when bin/bb-probe.exe, run.py or scripts/ differ from the list
    bbport-files.json); (None, []) without a list."""
    if not (install / 'scripts' / 'package_files.py').is_file():
        return None, []  # a release before the list
    return install_module(install, 'package_files').check(install)


def load_bin(path):
    b = path.read_bytes()
    _, base, n = struct.unpack_from('<8sQQ', b)
    o, writes = 24, []
    for _ in range(n):
        off, ln = struct.unpack_from('<QQ', b, o)
        o += 16
        writes.append((off, b[o:o + ln]))
        o += ln
    return base, writes


def bytes_of(writes):
    d = {}
    for off, data in writes:
        for i, c in enumerate(data):
            d[off + i] = c
    return d


def fps_mode(install, s):
    """The frame rate mode the game starts with: run.py takes bbport.ini's over the launcher's variable
    (1.9.5 on: the game's own PC Settings page writes it there), extra variables aside."""
    try:
        lines = (install / 'bbport.ini').read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        lines = []
    ini = dict(line.split('=', 1) for line in lines if '=' in line and not line.startswith('#'))
    value = ini.get('fps_mode', '').strip()
    return value if value in ('30', '60', '90', 'uncap') else s.get('fps_mode') or 'uncap'


def launcher_args(install, s):
    """--fps, --render-res, --output-res as run.py passes them for these settings."""
    sizes = subprocess.run([sys.executable, '-B', 'patches.py', '--print-scaled', '--settings', str(install / 'bbport.ini')],
                           cwd=install / 'scripts', capture_output=True, text=True).stdout.split()
    render, output = sizes if len(sizes) == 2 else ('', '')
    return ['--fps', fps_mode(install, s), '--render-res', render, '--output-res', output]


def run_patches(install, out, patches_dir, args, game):
    cmd = [sys.executable, '-B', 'patches.py', '--out', str(out), *args, '--extra', '',
           '--settings', str(install / 'bbport.ini'), '--game-dir', str(game),
           '--patches-dir', str(patches_dir), '--patches-config', str(install / 'patches.json')]
    r = subprocess.run(cmd, cwd=install / 'scripts', capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'patches.py failed: {(r.stderr.strip().splitlines() or ["no output"])[-1]}')
    return r.stdout + r.stderr


def model(install, s, patches_dir, work, minimal=True):
    """{'builtin': writes, 'full': writes, 'log': patches.py output, 'args': launcher arguments}."""
    game = folders(s, install)['game']
    if minimal:
        small = work / 'game'
        small.mkdir()
        for name in ('eboot.bin', 'sce_sys', 'sce_module'):
            (small / name).symlink_to(game / name)
        game = small
    full_out, base_out, empty = work / 'full', work / 'builtin', work / 'empty'
    for d in (full_out, base_out, empty):
        d.mkdir()
    subprocess.run([sys.executable, '-B', 'prepare.py', str(game), '--out', str(full_out)],
                   cwd=install / 'scripts', capture_output=True, text=True, check=True)
    for name in ('eboot.elf', 'analysis.json'):
        if (full_out / name).exists():
            shutil.copy2(full_out / name, base_out / name)
    args = launcher_args(install, s)
    log = run_patches(install, full_out, patches_dir, args, game)
    run_patches(install, base_out, empty, args, game)
    return {'builtin': load_bin(base_out / 'patches.bin')[1], 'full': load_bin(full_out / 'patches.bin')[1],
            'log': log, 'args': args}


def judge(install, patches_dir, m):
    """[(level, check, detail)] for the write model M: patch writes, overlaps, survival, red zone."""
    out = []
    windows, linux = xml_files(install, patches_dir)
    if [p.name for p in windows] != [p.name for p in linux]:
        out.append(('FAIL', 'patch file order', f'Windows applies {[p.name for p in windows]}, this model ran '
                    f'{[p.name for p in linux]}: rename files that differ in letter case only'))
    builtin, full = m['builtin'], m['full']
    if full[:len(builtin)] != builtin:
        return out + [('FAIL', 'patch writes', 'the built-in writes change when the external patches are added')]
    groups, rest = [('built-in', builtin)], full[len(builtin):]
    for g in re.finditer(r'Patches: external (.*) \((\d+) writes\)', m['log']):
        k = int(g.group(2))
        groups.append((g.group(1), rest[:k]))
        rest = rest[k:]
    builtin_names = re.search(r'writes from \[(.*)\]', m['log'])
    want = selected_entries(install, patches_dir)
    got = [(n, len(w)) for n, w in groups[1:]]
    missing = [f'{k} ({n})' for k, n in want if (k, n) not in got]
    extra = [f'{k} ({n})' for k, n in got if (k, n) not in want]
    ours_missing = [x for x in missing if x.startswith(OURS.name + '/')]
    out.append(('FAIL' if rest or ours_missing else 'WARN' if missing or extra else 'PASS', 'patch writes',
                f'{len(got)} of {len(want)} selected external entries applied, {len(full) - len(builtin)} writes; '
                f'built-in {len(builtin)} writes from {builtin_names.group(1) if builtin_names else "?"} '
                f'({" ".join(m["args"])})' + (f'; not applied: {missing}' if missing else '')
                + (f'; not selected: {extra}' if extra else '') + (f'; {len(rest)} unattributed' if rest else '')))
    maps = [(n, bytes_of(w)) for n, w in groups]
    clashes = []
    for i in range(len(maps)):
        for j in range(i + 1, len(maps)):
            common = maps[i][1].keys() & maps[j][1].keys()
            if common and frozenset({maps[i][0], maps[j][0]}) not in INTENDED:
                clashes.append(f'{maps[i][0]} <-> {maps[j][0]} ({len(common)} bytes at {min(common):#x})')
    out.append(('FAIL' if clashes else 'PASS', 'overlaps', '; '.join(clashes) if clashes else
                'none besides the intended title Exit Game pair'))
    final = bytes_of(full)
    ours = [(n, d) for n, d in maps if n.startswith(OURS.name + '/')]
    lost = [f'{n} ({sum(final.get(a) != v for a, v in d.items())} of {len(d)} bytes)'
            for n, d in ours if any(final.get(a) != v for a, v in d.items())]
    lost += [f'{x}: not applied at all' for x in ours_missing]
    out.append(('FAIL' if lost or not ours else 'PASS', 'survival', '; '.join(lost) if lost else
                f'{len(ours)} entries of {OURS.name}, every byte in the final list' if ours else
                f'no entry of {OURS.name} was applied'))
    rz = install / 'patches' / 'redzone.json'
    if not rz.exists():
        out.append(('WARN', 'red zone', f'{rz} not found (moved?): not checked'))
        return out
    sites = [(site[0], len(bytes.fromhex(site[1]))) for site in json.loads(rz.read_text())['sites']]
    hit = sorted({f'{off:#x}' for off, data in full[len(builtin):] for at, n in sites
                  if at < off + len(data) and off < at + n})
    out.append(('FAIL' if hit else 'PASS', 'red zone', f'external writes on rewritten store sites: {hit}' if hit
                else f'{len(sites)} sites, none touched by an external write'))
    return out
