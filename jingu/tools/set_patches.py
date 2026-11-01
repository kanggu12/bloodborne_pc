#!/usr/bin/env python3
"""Turn external patches on or off in the bbport launcher's patches.json
({"enabled": [...], "disabled": [...]}, keys "<file>/<patch name>"; it overrides each file's
isEnabled, scripts/patches.py external_selection()).

The launcher writes patches.json from its checkboxes when it starts the game or closes, so an
edit made while it is open is lost. As set_launcher_env.py: with --wait this waits until no
Bloodborne.exe (launcher) or bb-probe.exe (game) runs, then edits; the old file is copied to
BACKUP_DIR first; the new one is written the way the launcher writes it (json indent 2, ASCII,
CRLF) and read back. With --patches-dir, every --on key must name a patch in that folder.

  set_patches.py PATCHES_JSON [--on KEY ...] [--off KEY ...] --backup-dir DIR [--patches-dir DIR]
                 [--wait] [--hours 24] [--status FILE]
"""
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

from set_launcher_env import running, write_checked


def patch_keys(directory):
    keys = set()
    for path in sorted(p for p in directory.iterdir() if p.suffix.lower() == '.xml'):  # Windows: any letter case
        text = path.read_text(encoding='utf-8', errors='replace')
        keys |= {f'{path.name}/{name}' for name in re.findall(r'<Metadata\b[^>]*\bName="([^"]*)"', text)}
    return keys


def apply(config, on, off, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'patches.json.{time.strftime("%Y%m%d-%H%M%S")}'
    n = 1
    while backup.exists():
        n += 1
        backup = backup_dir / f'patches.json.{time.strftime("%Y%m%d-%H%M%S")}-{n}'
    shutil.copy2(config, backup)
    data = json.loads(config.read_text(encoding='utf-8'))
    enabled, disabled = set(data.get('enabled', [])), set(data.get('disabled', []))
    for key in off:
        enabled.discard(key)
        disabled.add(key)
    for key in on:
        disabled.discard(key)
        enabled.add(key)
    def verify(check):
        wrong = [k for k in on if k not in check['enabled'] or k in check['disabled']]
        wrong += [k for k in off if k in check['enabled'] or k not in check['disabled']]
        if wrong:
            raise RuntimeError(f'reads back wrong for {wrong}')
    write_checked(config, {'enabled': sorted(enabled), 'disabled': sorted(disabled)}, verify, ensure_ascii=True)
    return f'{len(on)} on, {len(off)} off (backup {backup})'


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('config', type=Path)
    p.add_argument('--on', action='append', default=[])
    p.add_argument('--off', action='append', default=[])
    p.add_argument('--backup-dir', type=Path, required=True)
    p.add_argument('--patches-dir', type=Path)
    p.add_argument('--wait', action='store_true')
    p.add_argument('--hours', type=float, default=24)
    p.add_argument('--status', type=Path)
    a = p.parse_args()
    if not a.on and not a.off:
        p.error('nothing to change: give --on or --off')
    if set(a.on) & set(a.off):
        p.error(f'both on and off: {sorted(set(a.on) & set(a.off))}')
    if a.patches_dir:
        missing = [k for k in a.on if k not in patch_keys(a.patches_dir)]
        if missing:
            p.error(f'not a patch in {a.patches_dir}: {missing}')
    deadline = time.monotonic() + a.hours * 3600

    def report(text):
        line = f'{time.strftime("%Y-%m-%d %H:%M:%S")} {text}'
        print(line)
        if a.status:
            a.status.write_text(line + '\n', encoding='utf-8')

    while True:
        busy = running()
        if not busy:
            time.sleep(3)  # the launcher writes patches.json as it closes
            busy = running()  # and may have been started again meanwhile
            if not busy:
                break
        if not a.wait:
            report(f'not applied: {", ".join(busy)} running (the launcher would overwrite the edit)')
            return 1
        if time.monotonic() > deadline:
            report(f'not applied: still running after {a.hours:g} h: {", ".join(busy)}')
            return 1
        time.sleep(5)
    try:
        report('applied: ' + apply(a.config, a.on, a.off, a.backup_dir))
    except Exception as error:  # noqa: BLE001 - reported to the status file
        report(f'failed: {error}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
