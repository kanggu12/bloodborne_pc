#!/usr/bin/env python3
"""Two small mods on top of a Korean translation mod that replaces the English texts. The game is
played without Vanilla Plus and Enhanced.

Each mod's folder is "<name> v<version> (Jin-Gu)", the version being the date its game files were
first made (versions.py: .2, .3 for more versions on one day). A run that makes the same game files
as a version in the mods folder keeps that folder and version (its README.txt is written again if it
differs); otherwise the files go into a new version's folder, under the version of a moved-out folder
with the same files if there is one. Every other version of the mod moves to
backups/old-mod-folders/<time>/ with a copy of mods.json, and mods.json gets the new name in the place
(and the on or off state) of the version it replaces. Folders are made, moved or renamed only while
neither the launcher nor the game runs: the launcher links the mods' files when it starts the game,
and it writes mods.json from what it shows.

1. Korean Translation Fix - Rebirth, Quit to Desktop and PC Settings: the texts of bbport's own features
(Quit to Desktop, the Doll's Rebirth that came with 1.9.4, and PC Settings in the game's System menu that
came with 1.9.5), which the translation mod replaces. "Korean Translation - Enhanced + Vanilla Plus" puts
Korean into the engus and enggb slots (menu.msgbnd.dcx); it loads after bbport's own layers and replaces
their texts, so the Doll's Rebirth choice reads ?ActionEventInfo? with empty questions, and the Quit to
Desktop rows lose their names (seen 2026-10-23 on 1.9.4); the PC Settings lines and pages would too.
It also gives the Chalice Dungeon gravestone list's additional rites without a name "알 수 없음",
not "?MenuText?".

For every language folder whose menu.msgbnd.dcx the translation mod replaces, the mod written here
holds that file plus
- the Quit to Desktop texts: bbport's own Korean (scripts/quit_menu.py TEXTS 'korkr', menu_texts)
- the PC Settings texts (scripts/pc_menu.py texts(): bbport has them in English for every language):
  PC_SETTINGS below is ours; a text not in it (a later bbport's) stays English, and the run says so
- the Rebirth texts in FMG 30 (scripts/rebirth.py ids): the Korean below is ours, in the translation
  mod's words (계몽 for Insight, 피의 유지 for Blood Echoes, the Doll's choices as "...한다"); the
  Insight cost comes from REBIRTH_INSIGHT.
Every other text is the translation mod's, checked before writing. The game reads it at its next
start. Run it again after the translation mod or bbport changes.

2. Korean Translation Fix - Item Texts without Vanilla Plus: the translation mod is made for Vanilla
Plus and describes
its versions of 69 existing items (other Caryll Runes under the same ids, Blood Echoes amounts, two
armour names). With Vanilla Plus off those entries take the game's official Korean text again
(dvdroot_ps4/msg/korkr/item.msgbnd.dcx); every other entry stays the translation mod's. Not made,
and its versions moved out, while a Vanilla Plus mod is enabled. It also names the Chalice Dungeon place ids
that have no text in any language: after their root dungeon, or "알 수 없는 성배 던전" for one of
another ritual than the game's ("?PlaceName?" in the gravestone list).

3. Korean Translation Fix - Chalice Dungeon Names with Vanilla Plus: those Chalice Dungeon names alone,
on the translation mod's item texts as they are (its Vanilla Plus versions of the items stay). Made in
place of 2 while a Vanilla Plus mod is enabled, and moved out while none is.

  korean_port_texts.py [--install DIR] [--settings FILE] [--source-mod NAME]
"""
import argparse
import json
import os
import re
import shutil
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import launch_model as lm  # noqa: E402
import versions  # noqa: E402
from set_launcher_env import running, write_checked  # noqa: E402

SOURCE_MOD = 'Korean Translation - Enhanced + Vanilla Plus'
AUTHOR = 'Jin-Gu'
OUT_MOD = 'Korean Translation Fix - Rebirth, Quit to Desktop and PC Settings'
ITEM_MOD = 'Korean Translation Fix - Item Texts without Vanilla Plus'
VPLUS_MOD = 'Korean Translation Fix - Chalice Dungeon Names with Vanilla Plus'
ITEM_MODS = (ITEM_MOD, VPLUS_MOD)  # both replace item.msgbnd.dcx: one at a time, by Vanilla Plus being on
OLD_FOLDERS = HERE.parent / 'backups' / 'old-mod-folders'
# the earlier names of the two mods (until 2026-10-24): never taken for Vanilla Plus
LEGACY = {OUT_MOD: ['Korean texts for bbport features', 'bbport 기능 한국어 대사',
                   # its name until 2026-11-01 (1.9.5 added PC Settings), every version it had
                   *(f'Korean Translation Fix - Rebirth and Quit to Desktop v{v} (Jin-Gu)'
                     for v in ('2026.10.23', '2026.10.25', '2026.10.25.2', '2026.10.25.3', '2026.10.25.4'))],
          ITEM_MOD: ['Korean item texts for the base game', 'Vanilla Plus 끈 상태용 아이템 대사']}
TMP = '.korean_port_texts.tmp'  # beside the mods folder: scripts/mods.py loads any folder inside it, dot or not


def rebirth_texts(cost):
    """(option, question, short, nothing) for the Doll's Rebirth, in Korean. 1.9.5 keeps what the equipped
    weapons need and undoes a rebirth left without regaining a level: the question says so, as bbport's own."""
    return ('다시 태어난다',
            f'계몽을 {cost} 소비하여 다시 태어나시겠습니까?\n'
            '능력치와 레벨이 처음 사냥꾼이 되었을 때로 돌아갑니다.\n'
            '(장비한 무기에 필요한 능력치는 유지됩니다.)\n'
            '잃은 레벨은 지금 또는 나중에 "피의 유지를 깃들인다"에서\n'
            '피의 유지 없이 되찾을 수 있습니다.\n'
            '레벨을 되찾지 않고 떠나면 취소됩니다.',
            f'다시 태어나려면 계몽이 {cost} 필요합니다.',
            '능력치가 이미 처음 사냥꾼이 되었을 때와 같습니다.')


# PC Settings (scripts/pc_menu.py texts(), by its English text). A help text "Applies after restart." is
# made of AFTER_RESTART below. On and Off are the translation mod's "ON" and "OFF", as on the game's own lines.
AFTER_RESTART = ' 재시작 후 적용됩니다.'
PC_SETTINGS = {
    'PC Graphics': 'PC 그래픽', 'PC Effects': 'PC 효과', 'PC Options': 'PC 옵션',
    'Upscaling, frame generation, resolution and frame rate.': '업스케일링, 프레임 생성, 해상도, 프레임 속도를 설정합니다.',
    'Model detail, shadows, reflections and post-processing effects.': '모델 디테일, 그림자, 반사, 후처리 효과를 설정합니다.',
    'Camera, HUD, button prompts and other PC options.': '카메라, HUD, 버튼 표시 등 PC 옵션을 설정합니다.',
    'Upscaler': '업스케일러',
    'Smooths edges and rebuilds detail at the output resolution.': '가장자리를 다듬고 출력 해상도에 맞게 디테일을 되살립니다.',
    'Upscaler Quality': '업스케일러 품질',
    'Scene resolution: Native is sharpest, Performance is fastest.': '장면 해상도입니다. "네이티브"가 가장 선명하고 "성능"이 가장 빠릅니다.',
    'Sharpness': '선명화 강도',
    'Sharpens the upscaled image.': '업스케일한 화면을 선명하게 합니다.',
    'Frame Generation': '프레임 생성',
    "Adds generated frames between the game's frames.": '게임 프레임 사이에 생성한 프레임을 넣습니다.',
    'Generated Frames': '생성 프레임 수',
    'Frames shown per game frame (DLSS on RTX 50 up to 4x).': '게임 프레임 하나당 보여 주는 프레임 수입니다(RTX 50의 DLSS는 4x까지).',
    'Output Resolution': '출력 해상도',
    'Final image size. Ultrawide sizes apply after restart.': '최종 화면 크기입니다. 울트라와이드 크기는 재시작 후 적용됩니다.',
    'Frame Rate': '프레임 속도',
    "The game's frame rate. Applies after restart.": '게임의 프레임 속도입니다.' + AFTER_RESTART,
    'Frame Cap': 'FPS 상한',
    'Limit of the unlocked frame rate. Applies after restart.': '프레임 속도가 "제한 없음"일 때의 상한입니다.' + AFTER_RESTART,
    'Model Detail': '모델 디테일',
    'Detail of distant models. Applies after restart.': '먼 모델의 디테일입니다.' + AFTER_RESTART,
    'Ambient Occlusion': '앰비언트 오클루전',
    'Contact shadows in corners. Applies after restart.': '모서리의 접촉 그림자입니다.' + AFTER_RESTART,
    'Dynamic Shadows': '동적 그림자',
    'Shadows of moving lights. Applies after restart.': '움직이는 조명의 그림자입니다.' + AFTER_RESTART,
    'Reflections': '반사',
    'Screen-space reflections on wet ground. Applies after restart.': '젖은 바닥의 화면 공간 반사입니다.' + AFTER_RESTART,
    'Anti-Aliasing': '안티 앨리어싱',
    "The game's own edge smoothing. Applies after restart.": '게임 자체의 가장자리 다듬기입니다.' + AFTER_RESTART,
    'Motion Blur': '모션 블러',
    'Blurs fast movement. Applies after restart.': '빠른 움직임을 흐리게 합니다.' + AFTER_RESTART,
    'Depth of Field': '피사계 심도',
    'Blurs what is out of focus. Applies after restart.': '초점 밖을 흐리게 합니다.' + AFTER_RESTART,
    'Chromatic Aberration': '색수차',
    'Colour fringes at the screen edges. Applies after restart.': '화면 가장자리의 색 번짐입니다.' + AFTER_RESTART,
    'Field of View': '시야각',
    'Camera field of view in degrees. Applies after restart.': '카메라 시야각(단위: 도)입니다.' + AFTER_RESTART,
    'Camera Distance': '카메라 거리',
    'Places the camera further back. Applies after restart.': '카메라를 더 뒤로 둡니다.' + AFTER_RESTART,
    'Auto Camera Rotation': '카메라 자동 회전',
    'Camera turns by itself while moving. Applies after restart.': '이동할 때 카메라가 저절로 돌아갑니다.' + AFTER_RESTART,
    'HUD Position': 'HUD 위치',
    'Ultrawide: moves the HUD toward the edges. Applies after restart.': '울트라와이드: HUD를 화면 가장자리 쪽으로 옮깁니다.' + AFTER_RESTART,
    'FPS Counter': 'FPS 카운터',
    'Shows the frame rate in a corner of the screen.': '화면 모서리에 프레임 속도를 표시합니다.',
    'Button Prompts': '버튼 아이콘',
    'Which buttons the game shows.': '게임에서 보여 줄 버튼 모양입니다.',
    'Mute in Background': '백그라운드 음소거',
    'Silences the game while another window is active.': '다른 창을 쓰는 동안 게임 소리를 끕니다.',
    'Skip Intro': '인트로 건너뛰기',
    'Skips the logos and opening movie. Applies after restart.': '로고와 오프닝 영상을 건너뜁니다.' + AFTER_RESTART,
    'Restart Game': '게임 재시작',
        'Restarts the game now to apply the changes marked for restart.': '지금 게임을 재시작하여 재시작이 필요한 변경 사항을 적용합니다.',
    'Restarts the game to apply the changes marked for restart.': '게임을 재시작하여 재시작이 필요한 변경 사항을 적용합니다.',
    'Restart the game now\nto apply the changes?': '지금 게임을 재시작하여\n변경 사항을 적용하시겠습니까?',
    'Off': 'OFF', 'Native': '네이티브', 'Quality': '품질', 'Balanced': '균형', 'Performance': '성능',
    'Ultra Performance': '초고성능', 'Unlocked': '제한 없음', 'Auto (display, max 120)': '자동(주사율, 최대 120)',
    'No limit': '제한 없음', '43 (default)': '43(기본)', 'Highest': '최고', 'High': '높음', 'Default': '기본',
    'Low': '낮음', 'Lowest': '최저', '100% (edges)': '100% (가장자리)', 'Auto': '자동',
    'Keyboard & Mouse': '키보드 및 마우스', 'Restart Now': '지금 재시작', 'AMD ML': 'AMD ML 4.0.1',
}
# Choice labels bbport_pc_menu.cpp looks up and scripts/pc_menu.py texts() lacks (FMG 200): the lists there end
# one short of the upscalers and frame generations it counts, so those entries read ?MenuText?.
PC_MISSING = {119106: 'FSR 4.1.2', 119144: 'AMD ML 4.0.2'}


def pc_settings(pc_menu, korean=None):
    """({FMG id: {text id: text}} of PC Settings in Korean, [the English texts without Korean: they stay])."""
    korean = PC_SETTINGS if korean is None else korean
    out, left = {}, []
    for fmg, strings in pc_menu.texts().items():
        out[fmg] = {}
        for sid, text in strings.items():
            out[fmg][sid] = korean.get(text, text)
            # names, sizes and numbers read the same in Korean: no word of English letters to translate
            if text not in korean and re.search(r'[A-Za-z]{3}', text) and not ASCII_NAMES.fullmatch(text):
                left.append(text)
    for sid, text in PC_MISSING.items():
        out.setdefault(200, {}).setdefault(sid, text)  # bbport's own label when a later release has one
    return out, sorted(set(left))


# Labels that are names in any language: upscalers, consoles
ASCII_NAMES = re.compile(r'(FSR [\d.]+|TAA|DLSS|AMD ML|PlayStation|Xbox|Switch|\d+ FPS)')


def font_characters(data):
    """The characters a font.gfx has glyphs for: the code table of its DefineFont3 (tag 75)."""
    if data[:3] != b'GFX' or len(data) < 16:
        raise ValueError('not a font.gfx')
    bits = data[8] >> 3  # the stage rectangle: 5 bits of size, then four fields of that size
    at = 8 + (5 + 4 * bits + 7) // 8 + 4  # then the frame rate and the frame count
    found = set()
    while at + 2 <= len(data):
        head = struct.unpack_from('<H', data, at)[0]
        code, length = head >> 6, head & 0x3f
        at += 2
        if length == 0x3f:
            length = struct.unpack_from('<I', data, at)[0]
            at += 4
        if code == 75:
            flags, name = data[at + 2], data[at + 4]
            p = at + 5 + name
            count = struct.unpack_from('<H', data, p)[0]
            p += 2
            wide_offsets, wide_codes = flags & 8, flags & 4
            size = 4 if wide_offsets else 2
            table = struct.unpack_from('<I' if wide_offsets else '<H', data, p + count * size)[0]
            codes = p + table
            found |= {chr(c) for c in (struct.unpack_from(f'<{count}H', data, codes) if wide_codes
                                       else data[codes:codes + count])}
        at += length
        if code == 0:
            break
    return found


def tables(quit_menu, archive):
    """{fmg id: {text id: text}} of a menu.msgbnd.dcx."""
    bnd = quit_menu.unpack_dcx(archive)
    return {fid: quit_menu.read_fmg(bnd[o:o + n]) for _e, o, n, fid in quit_menu.bnd4_files(bnd)}


def with_port_texts(quit_menu, rebirth, archive, pc=None):
    """ARCHIVE with the Quit to Desktop, PC Settings (PC: pc_settings's first) and the Rebirth texts, and the
    {(fmg, id): text} it set."""
    archive = quit_menu.menu_texts(archive, quit_menu.TEXTS['korkr'], pc)
    name, title_help, system_help, question = quit_menu.TEXTS['korkr']
    wanted = {(200, quit_menu.TITLE_ID): name, (200, quit_menu.SYSTEM_ID): name,
              (201, quit_menu.TITLE_ID): title_help, (201, quit_menu.SYSTEM_ID): system_help,
              (204, quit_menu.DIALOG_ID): question}
    wanted.update({(fmg, sid): text for fmg, strings in (pc or {}).items() for sid, text in strings.items()})
    ids = (rebirth.OPTION_TEXT, rebirth.QUESTION_TEXT, rebirth.SHORT_TEXT, rebirth.NOTHING_TEXT)
    texts = dict(zip(ids, rebirth_texts(rebirth.REBIRTH_INSIGHT)))
    bnd = quit_menu.unpack_dcx(archive)
    files = {fid: bnd[o:o + n] for _e, o, n, fid in quit_menu.bnd4_files(bnd)}
    strings = quit_menu.read_fmg(files[rebirth.TALK_FMG])
    strings.update(texts)
    archive = quit_menu.pack_dcx(archive, quit_menu.rebuild_bnd4(
        bnd, {rebirth.TALK_FMG: quit_menu.write_fmg(files[rebirth.TALK_FMG], strings)}))
    wanted.update({(rebirth.TALK_FMG, i): t for i, t in texts.items()})
    return archive, wanted


# What the gravestone list reads, from the 1.09 eboot (2026-10-25). The game's params, Vanilla Plus 1.20's and 1.25's and bb_enhanced's have the same Chalice
# Dungeon rows.
# Name (PlaceName, item FMG 19; FMG 120 is read first and has none): the HolygrailExParam row's name
# base (depth * 100000 + area * 1000, areas 0 Pthumeru to 3 Isz) plus, for a base of 0 or more, the
# part of the dungeon's first feature that has one, in the order of DungeonFeatureParam's order byte
# (of two features with one byte the later counts): 700 Cursed, 400 Sinister, 200 Rotted, 110 Fetid,
# none 000. The list shows no name for an id of 0 or below. That leaves 89 ids, and 51 of them have
# no text in any language (depths 6 to 8, and rites the rituals never add): a dungeon someone made
# with them (user report 2026-10-25: Depth 8 Pthumeru, row 6809, plays normally) reads "?PlaceName?".
# Every id of depths 1 to 9 and the four areas without text reads UNKNOWN_PLACE, and ..1 to ..8 of a
# labyrinth (no text in any language; the list never forms them) its root dungeon's name. The three
# rows without a name base (0, 6900, 6901) make the parts above 0 themselves: UNKNOWN_PLACE too (no
# other place is below 2100). Other places stay as they are.
PLACE_FMG = 19
CHALICE_DEPTHS, CHALICE_AREAS, RITE_PARTS = range(1, 10), range(4), (0, 110, 200, 400, 700)
UNKNOWN_PLACE, UNKNOWN = '알 수 없는 성배 던전', '알 수 없음'
# Additional rites (MenuText, menu FMG 200): the names of the features in the dungeon's four rite
# slots (5 to 8 of 9), the first field of each slot's DungeonFeatureParam row or, by a flag its caller
# passes, of its DungeonSubFeatLotParam row. Every rite feature and lot has a text there (2801xx,
# 2802xx); the other features have 0, and a slot whose row is missing reads 0 too. No language has
# MenuText 0, so those slots read "?MenuText?": NO_NAME reads UNKNOWN. What else could read MenuText
# 0: the 25 places with a fixed category show "?MenuText?" for a number without text, the text
# helpers skip 0 and below, and the one wrapper that returns no text as nothing is only called by a
# layout reader this install has no files for. So the text only takes the placeholder's place. The
# area texts 17100 to 17103 all have a text, and the rows hold areas 0 to 3 only.
# FMG 200 is written with bbport's write_fmg (a copy per entry, like the game's files): only FMG 19's
# tens of thousands of place ids need the shared copies of write_fmg below.
MENU_FMG, NO_NAME = 200, 0


def fill_texts(quit_menu, archive, fmg, fill, write=None):
    """ARCHIVE with FILL(strings of FMG) -> {id: text} set in that FMG (written by WRITE, default
    write_fmg below), and the {(fmg, id): text} set."""
    bnd = quit_menu.unpack_dcx(archive)
    files = {fid: bnd[o:o + n] for _e, o, n, fid in quit_menu.bnd4_files(bnd)}
    strings = quit_menu.read_fmg(files[fmg])
    texts = fill(strings)
    if not texts:
        return archive, {}
    strings.update(texts)
    archive = quit_menu.pack_dcx(archive, quit_menu.rebuild_bnd4(bnd, {fmg: (write or write_fmg)(files[fmg], strings)}))
    return archive, {(fmg, i): t for i, t in texts.items()}


def write_fmg(template, strings):
    """scripts/quit_menu.py write_fmg with each text stored once: the ids filled with the same text
    point at one copy (tens of thousands of place ids would otherwise add a copy each)."""
    ids = sorted(strings)
    groups = []
    for string_id in ids:
        if groups and groups[-1][2] == string_id - 1:
            groups[-1][2] = string_id
        else:
            groups.append([sum(g[2] - g[1] + 1 for g in groups), string_id, string_id])
    offsets_at = 0x28 + 16 * len(groups)
    text_at = offsets_at + 8 * len(ids)
    texts, at, slots = bytearray(), {}, []
    for string_id in ids:
        text = strings[string_id]
        if text is None:
            slots.append(0)
            continue
        if text not in at:
            at[text] = text_at + len(texts)
            texts += text.encode('utf-16-le') + b'\0\0'
        slots.append(at[text])
    out = bytearray(template[:0x28])
    struct.pack_into('<I', out, 0x0C, len(groups))
    struct.pack_into('<I', out, 0x10, len(ids))
    struct.pack_into('<Q', out, 0x18, offsets_at)
    for index, first, last in groups:
        out += struct.pack('<iiii', index, first, last, 0)
    for slot in slots:
        out += struct.pack('<q', slot)
    out += texts
    out += b'\0' * (4 + (-(len(out) + 4) % 4))  # the game's files end in zeros like this
    struct.pack_into('<I', out, 0x04, len(out))
    return bytes(out)


def chalice_place_names(strings):
    """{id: text} for the Chalice Dungeon place ids without text: ..1 to ..8 of a labyrinth its root
    dungeon's name, every other one of CHALICE_DEPTHS and CHALICE_AREAS and the RITE_PARTS above 0
    UNKNOWN_PLACE."""
    out = {sid: UNKNOWN_PLACE for sid in RITE_PARTS if sid > 0 and strings.get(sid) is None}
    for depth in CHALICE_DEPTHS:
        for area in CHALICE_AREAS:
            block = depth * 100000 + area * 1000
            for sid in range(block, block + 1000):
                if strings.get(sid) is None:
                    root = strings.get(sid - sid % 10)
                    out[sid] = root if root and 1 <= sid % 10 <= 8 else UNKNOWN_PLACE
    return out


def nameless_rites(strings):
    """{NO_NAME: UNKNOWN} when MenuText NO_NAME has no text."""
    return {NO_NAME: UNKNOWN} if strings.get(NO_NAME) is None else {}


def check(quit_menu, source, written, wanted):
    """'' when WRITTEN holds SOURCE's texts with exactly WANTED set on top, else what differs."""
    before, after = tables(quit_menu, source), tables(quit_menu, written)
    if before.keys() != after.keys():
        return f'FMG files differ: {sorted(before.keys() ^ after.keys())}'
    wrong = []
    for fid in before:
        for sid in before[fid].keys() | after[fid].keys():
            want = wanted.get((fid, sid), before[fid].get(sid))
            if after[fid].get(sid) != want:
                wrong.append((fid, sid))
    return f'texts differ at {wrong[:5]}' if wrong else ''


def write_file(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + '.tmp')
    tmp.write_bytes(data)
    os.replace(tmp, target)


def folder_name(mod, version):
    return f'{mod} v{version} ({AUTHOR})'


def version_pattern(mod):
    return re.compile(re.escape(mod) + r' v(' + versions.PATTERN + r') \(' + re.escape(AUTHOR) + r'\)')


def folder_versions(folder, mod):
    """{folder name: version} of MOD's version folders in FOLDER."""
    if not folder.is_dir():
        return {}
    pattern = version_pattern(mod)
    return {p.name: m.group(1) for p in folder.iterdir() if p.is_dir() and (m := pattern.fullmatch(p.name))}


def ours(name):
    return any(version_pattern(mod).fullmatch(name) for mod in (OUT_MOD, *ITEM_MODS))


def game_files(folder):
    """{path relative to FOLDER: bytes} of its files other than README.txt."""
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob('*'))
            if p.is_file() and p.relative_to(folder).as_posix() != 'README.txt'}


def new_version(mod, mods_dir, old_folders, day):
    """DAY, or DAY.N past every version of MOD of that day in MODS_DIR and in OLD_FOLDERS' runs."""
    used = set(folder_versions(mods_dir, mod).values())
    if old_folders.is_dir():
        for run in old_folders.iterdir():
            used |= set(folder_versions(run, mod).values())
    return versions.next_version(used, day)


def move_out(mods_dir, names, old_folders):
    """NAMES (folders of MODS_DIR) into a new run folder of OLD_FOLDERS; that folder, or None."""
    if not names:
        return None
    run = old_folders / time.strftime('%Y%m%d-%H%M%S')
    n = 1
    while run.exists():
        n += 1
        run = old_folders / f'{time.strftime("%Y%m%d-%H%M%S")}-{n}'
    run.mkdir(parents=True)
    for name in names:
        shutil.move(str(mods_dir / name), str(run / name))
    return run


def moved_out_version(mod, old_folders, files):
    """The newest version of MOD in OLD_FOLDERS' runs whose game files are exactly FILES, or None."""
    found = [v for run in (sorted(old_folders.iterdir()) if old_folders.is_dir() else [])
             for n, v in folder_versions(run, mod).items() if game_files(run / n) == files]
    return max(found, key=versions.key) if found else None


def standby(mod, files, readme, mods_dir, old_folders=OLD_FOLDERS, day=None):
    """The version of MOD with FILES kept out of the mods folder (the item mod of the other Vanilla Plus
    state): the moved-out one with these files, else a new version written into OLD_FOLDERS (a run
    named "<time>-standby"), so that the package and a later run find the same version."""
    version = moved_out_version(mod, old_folders, files)
    if version:
        return version
    version = new_version(mod, mods_dir, old_folders, day)
    run = old_folders / (time.strftime('%Y%m%d-%H%M%S') + '-standby')
    folder = run / folder_name(mod, version)
    for rel, data in files.items():
        write_file(folder / rel, data)
    (folder / 'README.txt').write_bytes(readme(version))
    print(f'{folder_name(mod, version)}: kept in {run} for the other Vanilla Plus state')
    return version


def busy_check(busy, what):
    now = busy()
    if now:
        raise SystemExit(f'{what}: {", ".join(now)} runs; mod folders are made or moved only while neither the '
                         'launcher nor the game runs: nothing changed')


def renamed_in_config(config, old, new, run):
    """mods.json (CONFIG) with NEW in the place of the first of OLD it lists and the others left out, NEW
    off if that one was off; the file as it was goes into RUN first. Written as the launcher writes it."""
    if not config or not config.is_file():
        return
    data = json.loads(config.read_text(encoding='utf-8'))
    order, disabled = list(data.get('order', [])), list(data.get('disabled', []))
    first = next((n for n in order if n in old), None)
    if first is None and not any(n in old for n in disabled):
        return
    shutil.copy2(config, run / 'mods.json')
    if new in order or new in disabled:  # listed already: it keeps its own place and state
        order, disabled, off = [n for n in order if n not in old], [n for n in disabled if n not in old], new in disabled
    else:
        order = [new if n == first else n for n in order if n == first or n not in old]
        off = first in disabled if first else any(n in old for n in disabled)
        disabled = [n for n in disabled if n not in old] + ([new] if off else [])
    want = dict(data, order=order, disabled=disabled)

    def verify(check):
        if check != want:
            raise RuntimeError('mods.json reads back wrong')
    write_checked(config, want, verify, ensure_ascii=True)
    print(f'mods.json: {new} in the place of {first or old}' + (', off as before' if off else ''))


def place(mods_dir, mod, files, readme, old_folders=OLD_FOLDERS, day=None, busy=running, config=None):
    """FILES ({path in the mod: bytes}, at least one) as MOD: kept in the version folder that already
    holds exactly them, else written into a new version's folder; the other versions move to
    OLD_FOLDERS and CONFIG (mods.json) names the new one in their place. README(version) becomes the
    folder's README.txt. The earlier names of MOD (LEGACY) move out as its other versions do. Returns
    the folder's name."""
    if not files:
        raise ValueError(f'{mod}: no game files to write')
    have = folder_versions(mods_dir, mod)
    same = sorted((n for n in have if game_files(mods_dir / n) == files), key=lambda n: versions.key(have[n]))
    keep = same[-1] if same else None
    others = [n for n in have if n != keep] + [n for n in LEGACY.get(mod, []) if (mods_dir / n).is_dir()]
    if keep is None or others:
        busy_check(busy, mod)
    if keep is None:
        version = moved_out_version(mod, old_folders, files) or new_version(mod, mods_dir, old_folders, day)
        keep = folder_name(mod, version)
        tmp = mods_dir.parent / TMP
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            for rel, data in files.items():
                write_file(tmp / keep / rel, data)
            os.replace(tmp / keep, mods_dir / keep)  # one rename: the new version appears whole or not at all
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print(f'{keep}: new version ({len(files)} files)')
    else:
        print(f'{keep}: unchanged, the same game files')
    text = readme(folder_versions(mods_dir, mod)[keep])
    note = mods_dir / keep / 'README.txt'
    if not note.is_file() or note.read_bytes() != text:
        note.write_bytes(text)
    run = move_out(mods_dir, others, old_folders)
    if run:
        print(f'{mod}: other versions {others} moved to {run}')
        renamed_in_config(config, others, keep, run)
    return keep


def official_items(quit_menu, source, official):
    """SOURCE (the translation mod's item.msgbnd.dcx) with every entry that differs from OFFICIAL's
    (the game's Korean) set back to OFFICIAL's, and the {(fmg, id): text} it set."""
    mod, ko = tables(quit_menu, source), tables(quit_menu, official)
    wanted = {(fid, sid): ko[fid][sid] for fid, table in mod.items() for sid, text in table.items()
              if text and text.strip() and (ko.get(fid, {}).get(sid) or '').strip()
              and text.strip() != ko[fid][sid].strip()}
    bnd = quit_menu.unpack_dcx(source)
    files = {fid: bnd[o:o + n] for _e, o, n, fid in quit_menu.bnd4_files(bnd)}
    replace = {}
    for fid in {f for f, _ in wanted}:
        strings = quit_menu.read_fmg(files[fid])
        strings.update({sid: text for (f, sid), text in wanted.items() if f == fid})
        replace[fid] = quit_menu.write_fmg(files[fid], strings)
    return quit_menu.pack_dcx(source, quit_menu.rebuild_bnd4(bnd, replace)), wanted


def drop_item_mod(mods_dir, why, mod=ITEM_MOD, old_folders=OLD_FOLDERS, busy=running):
    """MOD's versions (and its earlier names) out of MODS_DIR into a run of OLD_FOLDERS: (their names,
    that run), the run None when there were none."""
    have = [*folder_versions(mods_dir, mod), *(n for n in LEGACY.get(mod, []) if (mods_dir / n).is_dir())]
    if have:
        busy_check(busy, mod)
    run = move_out(mods_dir, have, old_folders)
    print(f'{mod}: not made, {why}' + (f'; {have} moved to {run}' if run else ''))
    return have, run


def vanilla_plus_on(mods, mods_dir, config):
    """The enabled Vanilla Plus mods (not the translation mod, not ours under any name)."""
    legacy = {n for names in LEGACY.values() for n in names}
    return [m for m in mods.selected(mods_dir, config) if 'vanilla' in m.casefold() and 'plus' in m.casefold()
            and 'translation' not in m.casefold() and not ours(m) and m not in legacy]


def mod_files(install, settings, source_mod=SOURCE_MOD, say=print):
    """{mod: {path in the mod: bytes}} our two mods hold when made from SOURCE_MOD and bbport's texts as
    installed now, each checked; nothing is written. The item mod is missing when SOURCE_MOD has no
    item.msgbnd.dcx."""
    s = lm.read_settings(settings)
    mods_dir = lm.folders(s, install)['mods']
    quit_menu = lm.install_module(install, 'quit_menu')
    if str(install / 'scripts') not in sys.path:
        sys.path.insert(0, str(install / 'scripts'))  # rebirth.py imports its neighbours
    rebirth = lm.install_module(install, 'rebirth')
    pc, left = pc_settings(lm.install_module(install, 'pc_menu'))
    if left:
        say(f'PC Settings: no Korean here for {left}: they stay English (PC_SETTINGS)')
    msg = mods_dir / source_mod / 'dvdroot_ps4' / 'msg'
    sources = sorted(msg.glob('*/menu.msgbnd.dcx'))
    if not sources:
        raise SystemExit(f'{msg}: no menu.msgbnd.dcx in {source_mod}')
    out = {OUT_MOD: {}}
    for source in sources:
        data = source.read_bytes()
        archive, wanted = with_port_texts(quit_menu, rebirth, data, pc)
        archive, rites = fill_texts(quit_menu, archive, MENU_FMG, nameless_rites, quit_menu.write_fmg)
        wanted.update(rites)
        problem = check(quit_menu, data, archive, wanted)
        if problem:
            raise SystemExit(f'{source.parent.name}: {problem}: nothing written')
        out[OUT_MOD][f'dvdroot_ps4/msg/{source.parent.name}/menu.msgbnd.dcx'] = archive
        say(f'{source.parent.name}/menu.msgbnd.dcx: {len(wanted)} texts on top of {source_mod}')
    official = lm.folders(s, install)['game'] / 'dvdroot_ps4' / 'msg' / 'korkr' / 'item.msgbnd.dcx'
    for source in sorted(msg.glob('*/item.msgbnd.dcx')):
        data = source.read_bytes()
        archive, wanted = official_items(quit_menu, data, official.read_bytes())
        archive, places = fill_texts(quit_menu, archive, PLACE_FMG, chalice_place_names)
        wanted.update(places)
        problem = check(quit_menu, data, archive, wanted)
        if problem:
            raise SystemExit(f'{ITEM_MOD} {source.parent.name}: {problem}: nothing written')
        out.setdefault(ITEM_MOD, {})[f'dvdroot_ps4/msg/{source.parent.name}/item.msgbnd.dcx'] = archive
        say(f'{source.parent.name}/item.msgbnd.dcx: {len(wanted) - len(places)} entries back to the official Korean, '
            f'{len(places)} Chalice Dungeon names')
        archive, places = fill_texts(quit_menu, data, PLACE_FMG, chalice_place_names)
        problem = check(quit_menu, data, archive, places)
        if problem:
            raise SystemExit(f'{VPLUS_MOD} {source.parent.name}: {problem}: nothing written')
        out.setdefault(VPLUS_MOD, {})[f'dvdroot_ps4/msg/{source.parent.name}/item.msgbnd.dcx'] = archive
    return out


def readme_text(mod, source_mod):
    if mod == VPLUS_MOD:
        return lambda version: (
            f'Vanilla Plus 를 켠 상태에서 성배 던전 이름을 채우는 대사입니다. 버전 {version}, 만든이: {AUTHOR}\r\n'
            '성배 던전 이름 중 게임 어느 언어에도 글이 없는 번호(비석 목록의 "?PlaceName?")에 그 던전의 이름을 넣고,\r\n'
            '게임에 없는 의식의 던전(깊이 8 등)에는 "알 수 없는 성배 던전" 을 넣습니다.\r\n'
            f'나머지 아이템 대사는 "{source_mod}" 그대로입니다(Vanilla Plus 판).\r\n'
            f'Vanilla Plus 를 끄면 이 모드 대신 "{ITEM_MOD}" 를 씁니다.\r\n'
            '켜고 끈 뒤에는 이 모드를 넣은 프로그램(jingu/tools/korean_port_texts.py)을 다시 실행하면 바꿔 넣습니다.\r\n'
            'jingu/tools/korean_port_texts.py 로 만들었습니다.\r\n').encode('utf-8-sig')
    if mod == OUT_MOD:
        return lambda version: (
            'bbport 의 자체 기능(인형의 "다시 태어난다", "바탕 화면으로 종료", 게임 시스템 메뉴의 "PC 그래픽·효과·옵션")에 쓰이는 한국어 대사입니다. '
            f'버전 {version}, 만든이: {AUTHOR}\r\n'
            f'"{source_mod}" 가 영어 자리의 메뉴 대사 파일을 통째로 바꿔서 이 대사들이 빠지던 것을, 그 파일에 대사를\r\n'
            '더한 사본으로 그 모드 뒤에 다시 넣습니다. 성배 던전 비석 목록의 추가 의법 칸 중 이름이 없는 것은\r\n'
            '"?MenuText?" 대신 "알 수 없음" 으로 나오게 합니다. 나머지 대사는 그 모드와 같습니다.\r\n'
            'jingu/tools/korean_port_texts.py 로 만들었습니다.\r\n').encode('utf-8-sig')
    return lambda version: (
        f'원래 게임(Vanilla Plus 없이)의 아이템 이름과 설명을 맞추는 대사입니다. 버전 {version}, 만든이: {AUTHOR}\r\n'
        f'"{source_mod}" 는 Vanilla Plus 용으로 만들어져, 기존 아이템 69개(카릴의 룬, 피의 유지 양 등)를\r\n'
        'Vanilla Plus 판으로 적고 있습니다. 이 모드는 그 항목들만 게임의 공식 한국어 대사로 되돌립니다.\r\n'
        '또 성배 던전 이름 중 게임 어느 언어에도 글이 없는 번호(비석 목록의 "?PlaceName?")에 그 던전의 이름을 넣고,\r\n'
        '게임에 없는 의식의 던전(깊이 8 등)에는 "알 수 없는 성배 던전" 을 넣습니다.\r\n'
        f'Vanilla Plus 를 켜면 이 모드 대신 "{VPLUS_MOD}" 를 씁니다.\r\n'
        '켜고 끈 뒤에는 이 모드를 넣은 프로그램(jingu/tools/korean_port_texts.py)을 다시 실행하면 바꿔 넣습니다.\r\n'
        'jingu/tools/korean_port_texts.py 로 만들었습니다.\r\n'
        ).encode('utf-8-sig')


def vanilla_plus_order_problem(order, on, source_mod):
    """What is wrong with ORDER (the load order) for the Vanilla Plus mods ON, or None: they have their
    own item and menu texts, so SOURCE_MOD's Korean ones must load after them."""
    late = [n for n in on if source_mod in order and n in order and order.index(n) > order.index(source_mod)]
    return f'load order {order}: {", ".join(late)} must come before {source_mod}' if late else None


def place_item_mod(mods_dir, config, files, on, source_mod, old_folders=OLD_FOLDERS, day=None, busy=running):
    """The item mod of the Vanilla Plus state (ON: the Vanilla Plus mods on) from FILES into MODS_DIR,
    the other one out of it (kept as a standby version in OLD_FOLDERS) and in mods.json (CONFIG) the
    one put in where the other one was."""
    use, other = (VPLUS_MOD, ITEM_MOD) if on else (ITEM_MOD, VPLUS_MOD)
    dropped, run = drop_item_mod(mods_dir, f'Vanilla Plus is on ({on})' if on else 'Vanilla Plus is off', other,
                                 old_folders, busy)
    if other in files:
        standby(other, files[other], readme_text(other, source_mod), mods_dir, old_folders, day)
    if use not in files:
        drop_item_mod(mods_dir, f'{source_mod} has no item.msgbnd.dcx', use, old_folders, busy)
        return None
    keep = place(mods_dir, use, files[use], readme_text(use, source_mod), old_folders, day, busy, config)
    if run:  # the item mod of the other state leaves its place and on/off state in mods.json to this one
        renamed_in_config(config, dropped, keep, run)
    return keep


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--install', type=Path, default=lm.INSTALL)
    p.add_argument('--settings', type=Path, default=lm.SETTINGS)
    p.add_argument('--source-mod', default=SOURCE_MOD)
    a = p.parse_args()
    s = lm.read_settings(a.settings)
    mods_dir = lm.folders(s, a.install)['mods']
    config = a.install / 'mods.json'
    files = mod_files(a.install, a.settings, a.source_mod)
    mods = lm.install_module(a.install, 'mods')
    on = vanilla_plus_on(mods, mods_dir, config)
    problem = vanilla_plus_order_problem(mods.selected(mods_dir, config), on, a.source_mod)
    if problem:
        raise SystemExit(f'{problem}: move it up in the launcher\'s mod list (mods.json); nothing changed')
    place(mods_dir, OUT_MOD, files[OUT_MOD], config=config, readme=readme_text(OUT_MOD, a.source_mod))
    place_item_mod(mods_dir, config, files, on, a.source_mod)
    order = mods.selected(mods_dir, config)
    for name in [m for mod in (OUT_MOD, *ITEM_MODS) for m in folder_versions(mods_dir, mod)]:
        if name not in order:
            print(f'{name}: off in mods.json')
        elif a.source_mod in order and order.index(name) < order.index(a.source_mod):
            raise SystemExit(f'load order {order}: {name} must come after {a.source_mod} (mods.json)')
    print(f'load order: {" > ".join(order)}; the game reads it at its next start')
    return 0


if __name__ == '__main__':
    sys.exit(main())
