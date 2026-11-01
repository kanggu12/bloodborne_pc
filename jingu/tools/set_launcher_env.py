#!/usr/bin/env python3
"""Add or replace one NAME=VALUE in the bbport launcher's Extra variables (settings.json
`extra_env`, passed to the game as environment variables).

The launcher writes settings.json from its own state when it starts the game or closes, so an
edit made while it is open is lost. With --wait this waits until no Bloodborne.exe (launcher)
or bb-probe.exe (game) runs, then edits. The old file is copied to BACKUP_DIR first; the new
one is written the way the launcher writes it (json indent 2, UTF-8, CRLF) and read back.

  set_launcher_env.py SETTINGS NAME=VALUE --backup-dir DIR [--wait] [--status FILE]
  set_launcher_env.py SETTINGS KEY=VALUE --key --backup-dir DIR    a top-level setting (e.g. draw_pipe=0)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROCESSES = ('bloodborne.exe', 'bb-probe.exe')


def running():
    """Names of the launcher or game processes that run. A tasklist that cannot run or lists nothing
    counts as busy: editing then could race the launcher."""
    try:
        r = subprocess.run(['tasklist.exe', '/fo', 'csv', '/nh'], capture_output=True, text=True, errors='replace')
    except OSError as error:
        return [f'(tasklist.exe unavailable: {error})']
    out = r.stdout.lower()
    if r.returncode or '"' not in out:
        return [f'(tasklist.exe failed, exit {r.returncode})']
    return [name for name in PROCESSES if f'"{name}"' in out]


def write_checked(path, data, verify, ensure_ascii=False):
    """Write DATA (a JSON document, indent 2, CRLF as the launcher writes it) beside PATH, read it back
    through VERIFY (raises when wrong), then rename it over PATH: a wrong or failed write leaves the
    old file as it was. settings.json is UTF-8; patches.json is ASCII with \\u escapes (ensure_ascii)."""
    tmp = path.with_name(path.name + '.tmp')
    try:
        tmp.write_bytes(json.dumps(data, indent=2, ensure_ascii=ensure_ascii).replace('\n', '\r\n').encode('utf-8'))
        check = json.loads(tmp.read_text(encoding='utf-8'))
        verify(check)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return check


def apply(settings, item, backup_dir, key=False):
    name = item.split('=', 1)[0]
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'settings.json.{time.strftime("%Y%m%d-%H%M%S")}'
    n = 1
    while backup.exists():
        n += 1
        backup = backup_dir / f'settings.json.{time.strftime("%Y%m%d-%H%M%S")}-{n}'
    shutil.copy2(settings, backup)
    data = json.loads(settings.read_text(encoding='utf-8'))
    if key:
        value = item.split('=', 1)[1]
        if name not in data:
            raise RuntimeError(f'{name} is not a launcher setting')
        old = data[name]
        if isinstance(old, bool):  # keep the setting's JSON type: "false" as a string would read as on
            if value.lower() not in ('true', 'false'):
                raise RuntimeError(f'{name} is true/false, not {value!r}')
            value = value.lower() == 'true'
        elif isinstance(old, (int, float)):
            value = json.loads(value)
        elif not isinstance(old, str):
            raise RuntimeError(f'{name} holds a {type(old).__name__}: not changed by this tool')
        data[name] = value
    else:
        items = [x for x in str(data.get('extra_env', '')).split() if x.split('=', 1)[0] != name]
        items.append(item)
        data['extra_env'] = ' '.join(items)

    def verify(check):
        if key and check.get(name) != value:
            raise RuntimeError(f'{name} reads back as {check.get(name)!r}')
        if not key and item not in str(check.get('extra_env', '')).split():
            raise RuntimeError(f'extra_env reads back as {check.get("extra_env")!r}')
    check = write_checked(settings, data, verify)
    if key:
        return f'{name} = {check[name]!r} (backup {backup})'
    return f'extra_env = {check["extra_env"]!r} (backup {backup})'


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('settings', type=Path)
    p.add_argument('item')
    p.add_argument('--backup-dir', type=Path, required=True)
    p.add_argument('--wait', action='store_true')
    p.add_argument('--key', action='store_true', help='item is a top-level setting, not an Extra variable')
    p.add_argument('--hours', type=float, default=24)
    p.add_argument('--status', type=Path)
    a = p.parse_args()
    if '=' not in a.item or not a.item.split('=', 1)[0]:
        p.error('item must be NAME=VALUE')
    deadline = time.monotonic() + a.hours * 3600

    def report(text):
        line = f'{time.strftime("%Y-%m-%d %H:%M:%S")} {text}'
        print(line)
        if a.status:
            a.status.write_text(line + '\n')

    while True:
        busy = running()
        if not busy:
            time.sleep(3)  # the launcher writes settings.json as it closes
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
        report('applied: ' + apply(a.settings, a.item, a.backup_dir, a.key))
    except Exception as error:  # noqa: BLE001 - reported to the status file
        report(f'failed: {error}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
