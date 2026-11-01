#!/usr/bin/env python3
"""Tests for the version folders of tools/korean_port_texts.py (place, new_version, ours) on a
temporary mods folder: a first run makes "<mod> v<day> (Jin-Gu)", the same game files keep that
folder and version, other files make the next version of the day past every one kept in the old
folders (files a moved-out version has get its version back), the other versions move out whole and
mods.json names the new one in their place, a write that stops halfway leaves nothing in the mods
folder, and nothing is made or moved while the launcher or the game runs."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / 'tools'
sys.path.insert(0, str(TOOLS))
import korean_port_texts as kpt  # noqa: E402
import versions  # noqa: E402

MOD = kpt.OUT_MOD
FILES = {'dvdroot_ps4/msg/engus/menu.msgbnd.dcx': b'one', 'dvdroot_ps4/msg/enggb/menu.msgbnd.dcx': b'two'}


def readme(version):
    return f'version {version}'.encode()


class Versions(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.mods = self.root / 'mods'
        self.mods.mkdir()
        (self.mods / 'Other mod').mkdir()
        self.old = self.root / 'old'
        self.config = self.root / 'mods.json'

    def place(self, files, day='2026.10.24', busy=lambda: [], config=None):
        return kpt.place(self.mods, MOD, files, readme, old_folders=self.old, day=day, busy=busy, config=config)

    def folders(self):
        return sorted(p.name for p in self.mods.iterdir())

    def test_first_same_and_new_versions(self):
        first = self.place(FILES)
        self.assertEqual(first, f'{MOD} v2026.10.24 (Jin-Gu)')
        self.assertEqual(kpt.game_files(self.mods / first), FILES)
        self.assertEqual((self.mods / first / 'README.txt').read_bytes(), b'version 2026.10.24')
        self.assertEqual(self.place(dict(FILES), day='2026.10.25'), first, 'the same files keep their version')
        self.assertEqual(self.folders(), [first, 'Other mod'])
        second = self.place({**FILES, 'dvdroot_ps4/msg/engus/menu.msgbnd.dcx': b'changed'})
        self.assertEqual(second, f'{MOD} v2026.10.24.2 (Jin-Gu)')
        self.assertEqual(self.folders(), [second, 'Other mod'])
        (run,) = self.old.iterdir()
        self.assertEqual(kpt.game_files(run / first), FILES, 'the old version moved out whole')
        again = self.place(FILES)  # back to the first files: their version again, the moved-out copy kept
        self.assertEqual(again, first)
        self.assertEqual(len(list(self.old.iterdir())), 2)
        self.assertEqual(self.place({'b': b'new'}), f'{MOD} v2026.10.24.3 (Jin-Gu)')
        self.assertFalse((self.root / kpt.TMP).exists(), 'no temporary folder left')

    def test_the_old_name_moves_out_and_the_new_one_takes_its_place(self):
        old = 'Korean Translation Fix - Rebirth and Quit to Desktop v2026.10.25.4 (Jin-Gu)'
        self.assertIn(old, kpt.LEGACY[MOD], 'every version it had is listed')
        kpt.write_file(self.mods / old / 'dvdroot_ps4/msg/engus/menu.msgbnd.dcx', b'old')
        self.config.write_text(json.dumps({'order': ['Base', old, 'Next'], 'disabled': []}))
        new = self.place(FILES, config=self.config, day='2026.11.01')
        self.assertEqual(new, f'{MOD} v2026.11.01 (Jin-Gu)')
        self.assertEqual(self.folders(), [new, 'Other mod'])
        self.assertEqual(json.loads(self.config.read_text()), {'order': ['Base', new, 'Next'], 'disabled': []})

    def test_versions_moved_out_still_count(self):
        first = self.place(FILES)
        kpt.move_out(self.mods, [first], self.old)  # as with Vanilla Plus turned on
        self.assertEqual(self.place({'a': b'x'}), f'{MOD} v2026.10.24.2 (Jin-Gu)', 'a version is never used twice')

    def test_a_listed_kept_version_keeps_its_own_place(self):
        a = self.mods / kpt.folder_name(MOD, '2026.10.23')
        b = self.mods / kpt.folder_name(MOD, '2026.10.24')
        for folder, files in ((a, FILES), (b, {'a': b'x'})):
            for rel, data in files.items():
                kpt.write_file(folder / rel, data)
        self.config.write_text(json.dumps({'order': ['Base', a.name, b.name], 'disabled': [b.name]}))
        self.assertEqual(self.place(FILES, config=self.config), a.name)
        self.assertEqual(json.loads(self.config.read_text()), {'order': ['Base', a.name], 'disabled': []})

    def test_earlier_names_are_not_vanilla_plus(self):
        class Mods:
            @staticmethod
            def selected(_root, _config):
                return ['Vanilla Plus 끈 상태용 아이템 대사', f'{kpt.ITEM_MOD} v2026.10.23 (Jin-Gu)',
                        f'{kpt.VPLUS_MOD} v2026.10.24 (Jin-Gu)', 'Korean Translation - Enhanced + Vanilla Plus']
        self.assertEqual(kpt.vanilla_plus_on(Mods, self.mods, self.config), [])
        Mods.selected = staticmethod(lambda _r, _c: ['Vanilla_Plus_v1.25'])
        self.assertEqual(kpt.vanilla_plus_on(Mods, self.mods, self.config), ['Vanilla_Plus_v1.25'])

    def test_a_day_without_versions_has_no_suffix(self):
        self.place(FILES, day='2026.10.23')
        self.assertEqual(self.place({'a': b'x'}, day='2026.10.24'), f'{MOD} v2026.10.24 (Jin-Gu)')

    def test_two_versions_there_keep_the_one_with_these_files(self):
        a = self.mods / kpt.folder_name(MOD, '2026.10.23')
        b = self.mods / kpt.folder_name(MOD, '2026.10.24')
        for folder, files in ((a, FILES), (b, {'a': b'x'})):
            for rel, data in files.items():
                kpt.write_file(folder / rel, data)
        self.assertEqual(self.place(FILES), a.name)
        self.assertEqual(self.folders(), [a.name, 'Other mod'])

    def test_nothing_changes_while_the_launcher_or_the_game_runs(self):
        first = self.place(FILES)
        for name in ('bb-probe.exe', 'bloodborne.exe'):  # the launcher links the mods' files at the start
            with self.assertRaises(SystemExit):
                self.place({'a': b'x'}, busy=lambda: [name])
            self.assertEqual(self.folders(), [first, 'Other mod'])
            self.assertFalse(self.old.exists())
        self.assertEqual(self.place(FILES, busy=lambda: ['bb-probe.exe']), first, 'the same files need no move')

    def test_a_write_that_stops_leaves_nothing_in_the_mods_folder(self):
        first = self.place(FILES)
        real = kpt.write_file
        calls = []

        def failing(target, data):
            calls.append(target)
            if len(calls) == 2:
                raise OSError('disk full')
            real(target, data)
        kpt.write_file = failing
        try:
            with self.assertRaises(OSError):
                self.place({'a': b'1', 'b': b'2'})
        finally:
            kpt.write_file = real
        self.assertTrue(all(self.mods not in c.parents for c in calls), 'written beside the mods folder')
        self.assertEqual(self.folders(), [first, 'Other mod'])
        self.assertFalse((self.root / kpt.TMP).exists())
        with self.assertRaises(ValueError):
            self.place({})

    def test_mods_json_names_the_new_version_in_the_old_place(self):
        first = self.place(FILES)
        self.config.write_text(json.dumps({'order': ['A', first, 'B'], 'disabled': ['B', first]}, indent=2))
        second = self.place({'a': b'x'}, config=self.config)
        data = json.loads(self.config.read_text())
        self.assertEqual(data, {'order': ['A', second, 'B'], 'disabled': ['B', second]})
        raw = self.config.read_bytes()
        self.assertTrue(raw.isascii() and raw.count(b'\n') == raw.count(b'\r\n'), 'as the launcher writes it')
        (run,) = self.old.iterdir()
        self.assertEqual(json.loads((run / 'mods.json').read_text())['order'], ['A', first, 'B'])
        self.place({'a': b'x'}, config=self.config)  # nothing replaced: mods.json stays
        self.assertEqual(json.loads(self.config.read_text())['order'], ['A', second, 'B'])

    def test_names(self):
        self.assertTrue(kpt.ours(f'{kpt.ITEM_MOD} v2026.10.23 (Jin-Gu)'))
        self.assertTrue(kpt.ours(f'{MOD} v2026.10.24.12 (Jin-Gu)'))
        for name in (MOD, f'{MOD} v2026.10.24', f'{MOD} v2026.10.24 (Jin-Gu) copy', 'Vanilla_Plus_v1.25',
                     'Korean Translation - Enhanced + Vanilla Plus'):
            self.assertFalse(kpt.ours(name), name)
        self.assertLess(versions.key('2026.10.24'), versions.key('2026.10.24.2'))
        self.assertLess(versions.key('2026.10.24.9'), versions.key('2026.10.24.10'))
        self.assertLess(versions.key('2026.10.24.9'), versions.key('2026.10.25'))


    def test_standby_keeps_one_version_per_files(self):
        mod = kpt.VPLUS_MOD
        v1 = kpt.standby(mod, {'a': b'1'}, readme, self.mods, old_folders=self.old, day='2026.10.24')
        self.assertEqual(v1, '2026.10.24')
        self.assertEqual(kpt.standby(mod, {'a': b'1'}, readme, self.mods, old_folders=self.old, day='2026.10.25'), v1)
        v2 = kpt.standby(mod, {'a': b'2'}, readme, self.mods, old_folders=self.old, day='2026.10.24')
        self.assertEqual(v2, '2026.10.24.2')
        self.assertEqual(kpt.moved_out_version(mod, self.old, {'a': b'2'}), v2)
        self.assertEqual(self.folders(), ['Other mod'], 'nothing goes into the mods folder')


class VanillaPlusFlip(unittest.TestCase):
    """place_item_mod as Vanilla Plus is turned on and off: one item mod in the mods folder, the other
    kept out, mods.json naming the one put in where the other was (and as off as it was)."""
    FILES = {kpt.ITEM_MOD: {'msg/item': b'official'}, kpt.VPLUS_MOD: {'msg/item': b'vplus'}}

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.mods = self.root / 'mods'
        self.mods.mkdir()
        self.old = self.root / 'old'
        self.config = self.root / 'mods.json'

    def flip(self, on, busy=lambda: []):
        return kpt.place_item_mod(self.mods, self.config, self.FILES, on, kpt.SOURCE_MOD, self.old, '2026.10.25', busy)

    def test_turning_vanilla_plus_on_and_off(self):
        item = self.flip([])
        self.config.write_text(json.dumps({'order': [kpt.SOURCE_MOD, item, 'Other'], 'disabled': [item]}))
        vplus = self.flip(['Vanilla_Plus_v1.25'])
        self.assertTrue(vplus.startswith(kpt.VPLUS_MOD))
        self.assertEqual(sorted(p.name for p in self.mods.iterdir()), [vplus])
        self.assertEqual(json.loads(self.config.read_text()),
                         {'order': [kpt.SOURCE_MOD, vplus, 'Other'], 'disabled': [vplus]}, 'its place and its off')
        self.assertEqual(self.flip([]), item, 'the files of the first version: its version again')
        self.assertEqual(sorted(p.name for p in self.mods.iterdir()), [item])
        self.assertEqual(json.loads(self.config.read_text()),
                         {'order': [kpt.SOURCE_MOD, item, 'Other'], 'disabled': [item]})

    def test_an_earlier_name_of_the_item_mod_moves_out_with_vanilla_plus_off(self):
        legacy = self.mods / kpt.LEGACY[kpt.ITEM_MOD][0]
        kpt.write_file(legacy / 'msg' / 'item', b'old')
        self.config.write_text(json.dumps({'order': [kpt.SOURCE_MOD, legacy.name, 'Other'], 'disabled': []}))
        item = self.flip([])
        self.assertEqual(sorted(p.name for p in self.mods.iterdir()), [item])
        self.assertEqual(json.loads(self.config.read_text())['order'], [kpt.SOURCE_MOD, item, 'Other'])

    def test_vanilla_plus_must_load_before_the_translation(self):
        src = kpt.SOURCE_MOD
        self.assertIsNone(kpt.vanilla_plus_order_problem(['V', src, 'ours'], ['V'], src))
        self.assertIn('V must come before', kpt.vanilla_plus_order_problem([src, 'V'], ['V'], src))
        self.assertIsNone(kpt.vanilla_plus_order_problem([src, 'V'], [], src))

    def test_an_earlier_name_of_the_item_mod_moves_out_with_vanilla_plus(self):
        legacy = self.mods / kpt.LEGACY[kpt.ITEM_MOD][1]
        kpt.write_file(legacy / 'msg' / 'item', b'old')
        self.config.write_text(json.dumps({'order': [kpt.SOURCE_MOD, legacy.name], 'disabled': []}))
        vplus = self.flip(['Vanilla_Plus_v1.25'])
        self.assertEqual(sorted(p.name for p in self.mods.iterdir()), [vplus])
        self.assertEqual(json.loads(self.config.read_text())['order'], [kpt.SOURCE_MOD, vplus])

    def test_nothing_moves_while_the_game_runs(self):
        item = self.flip([])
        with self.assertRaises(SystemExit):
            self.flip(['Vanilla_Plus_v1.25'], busy=lambda: ['bb-probe.exe'])
        self.assertEqual(sorted(p.name for p in self.mods.iterdir()), [item])


class ChaliceTexts(unittest.TestCase):
    def test_place_names_take_the_root_dungeons(self):
        strings = {2100: 'Dream', 2101: None, 100000: 'Laby', 100001: None, 100008: None, 100009: 'Laby (F)',
                   100110: 'Fetid', 201000: '', 201001: None}
        names = kpt.chalice_place_names(strings)
        self.assertEqual((names[100001], names[100008]), ('Laby', 'Laby'))
        self.assertEqual(names[201001], kpt.UNKNOWN_PLACE, 'a root without text names nothing')
        self.assertEqual(names[100005], 'Laby', 'missing next to a root with text: its name too')
        for sid in (800000, 800110, 803999, 100100, 900002):  # depth 8 of a ritual the game has not
            self.assertEqual(names[sid], kpt.UNKNOWN_PLACE, sid)
        for sid in (110, 200, 400, 700):  # the three rows without a name base
            self.assertEqual(names[sid], kpt.UNKNOWN_PLACE, sid)
        self.assertFalse({0, 2100, 2101, 100000, 100009, 100110, 1, 100, 701} & names.keys(),
                         'texts, other places and 0 (the list shows no name for it) stay')
        self.assertFalse([i for i in names if i not in kpt.RITE_PARTS and (i % 100000 >= 4000 or not 100000 <= i < 1000000)],
                         'four areas, depths 1 to 9')
        self.assertEqual(len(names), 9 * 4 * 1000 - 4 + 4)  # the four with a text, empty or not

    def test_a_rite_without_a_name_reads_unknown(self):
        self.assertEqual(kpt.nameless_rites({17104: '', 266306: '-', 280110: 'Fetid'}), {0: kpt.UNKNOWN})
        self.assertEqual(kpt.nameless_rites({0: None}), {0: kpt.UNKNOWN}, 'an entry without text reads the placeholder too')
        self.assertEqual(kpt.nameless_rites({0: ''}), {}, 'an empty text is a text')
        self.assertEqual(kpt.nameless_rites({0: 'x'}), {})

    def test_one_copy_of_each_text(self):
        quit_menu = kpt.lm.install_module(kpt.lm.INSTALL, 'quit_menu')
        template = quit_menu.write_fmg(b'\0' * 0x28, {1: 'a'})
        strings = {1: 'a', 2: None, 3: 'a', 10: 'b', **dict.fromkeys(range(20, 2000), 'same')}
        data = kpt.write_fmg(template, strings)
        self.assertEqual(quit_menu.read_fmg(data), strings)
        self.assertLess(len(data), len(quit_menu.write_fmg(template, strings)) / 2)
        distinct = {1: 'a', 2: None, 5: 'b'}
        self.assertEqual(kpt.write_fmg(template, distinct), quit_menu.write_fmg(template, distinct))

    @unittest.skipUnless((kpt.lm.INSTALL / 'Game').is_dir(), 'needs the install')
    def test_the_mods_made_from_this_install(self):
        made = kpt.mod_files(kpt.lm.INSTALL, kpt.lm.SETTINGS, say=lambda _l: None)
        quit_menu = kpt.lm.install_module(kpt.lm.INSTALL, 'quit_menu')
        for lang in ('engus', 'enggb'):
            item = kpt.tables(quit_menu, made[kpt.ITEM_MOD][f'dvdroot_ps4/msg/{lang}/item.msgbnd.dcx'])[19]
            self.assertEqual(item[100001], item[100000])
            self.assertEqual(item[503008], item[503000])
            self.assertIsNone(item[2101], 'a place outside the Chalice Dungeons stays without text')
            blank = [i for i, t in item.items() if i >= 100000 and t is None]
            self.assertEqual(blank, [])
            # with Vanilla Plus: the translation mod's item texts as they are, the names filled alone
            rel = f'dvdroot_ps4/msg/{lang}/item.msgbnd.dcx'
            base = kpt.tables(quit_menu, (kpt.lm.folders(kpt.lm.read_settings(kpt.lm.SETTINGS), kpt.lm.INSTALL)['mods']
                                          / kpt.SOURCE_MOD / rel).read_bytes())
            vplus = kpt.tables(quit_menu, made[kpt.VPLUS_MOD][rel])
            changed = {(f, i) for f in base for i in base[f].keys() | vplus[f].keys() if base[f].get(i) != vplus[f].get(i)}
            self.assertEqual(changed, {(19, i) for i in kpt.chalice_place_names(base[19])})
            roots = [i for i in base[19] if i >= 100000 and base[19][i] is None and 1 <= i % 10 <= 8 and base[19].get(i - i % 10)]
            self.assertEqual(len(roots), 80)  # ten labyrinths, ..1 to ..8
            self.assertEqual([vplus[19][i] for i in roots], [base[19][i - i % 10] for i in roots])
            self.assertEqual(vplus[19][800000], kpt.UNKNOWN_PLACE)
            bnd = quit_menu.unpack_dcx(made[kpt.VPLUS_MOD][rel])
            fmg19 = next(n for _e, _o, n, fid in quit_menu.bnd4_files(bnd) if fid == 19)
            self.assertLess(fmg19, 400_000, 'one copy of the name (a copy each: 1.2 MB)')
            self.assertNotEqual(made[kpt.VPLUS_MOD][rel], made[kpt.ITEM_MOD][rel])
            rel = f'dvdroot_ps4/msg/{lang}/menu.msgbnd.dcx'
            menu = kpt.tables(quit_menu, made[kpt.OUT_MOD][rel])[200]
            source = kpt.tables(quit_menu, (kpt.lm.folders(kpt.lm.read_settings(kpt.lm.SETTINGS), kpt.lm.INSTALL)['mods']
                                            / kpt.SOURCE_MOD / rel).read_bytes())[200]
            self.assertEqual(menu[0], kpt.UNKNOWN)
            # the areas and rites the list never reads keep the translation mod's texts
            self.assertEqual({i: menu.get(i) for i in (17104, 17105, 17106, 17109, 266307, 266399)},
                             {i: source.get(i) for i in (17104, 17105, 17106, 17109, 266307, 266399)})
            self.assertEqual([menu.get(i) for i in (266306, 280110, 280111, 280800)], ['-', '죽은 악취의 공물', None, None])
            self.assertTrue(menu[17103] and menu[17103] != kpt.UNKNOWN)


def chalice_rows(quit_menu, path):
    """{param: {row id: row}} of the Chalice Dungeon params in a gameparam.parambnd.dcx."""
    bnd = quit_menu.unpack_dcx(path.read_bytes())
    assert bnd[0x30], 'file names in UTF-16'
    out = {}
    for e, o, n, _fid in quit_menu.bnd4_files(bnd):
        at = end = struct.unpack_from('<I', bnd, e + 0x20)[0]
        while bnd[end:end + 2] != b'\0\0':
            end += 2
        name = bnd[at:end].decode('utf-16-le').split('\\')[-1]
        if name in ROW_SIZES:
            data = bnd[o:o + n]
            count, = struct.unpack_from('<H', data, 0x0A)
            rows = [struct.unpack_from('<IIQQ', data, 0x40 + i * 0x18) for i in range(count)]
            out[name] = {rid: data[row:row + ROW_SIZES[name]] for rid, _pad, row, _name in rows}
    return out


# The rows' sizes, and the fields the gravestone list reads (README "성배 던전 비석 목록이 읽는 번호")
ROW_SIZES = {'HolygrailExParam.param': 136, 'DungeonFeatureParam.param': 36, 'DungeonSubFeatLotParam.param': 60}


@unittest.skipUnless((kpt.lm.INSTALL / 'Game').is_dir(), 'needs the install')
class PcSettings(unittest.TestCase):
    """PC Settings (1.9.5): its texts in Korean on top of what bbport has in English."""

    class Menu:
        @staticmethod
        def texts():
            return {200: {1: 'Off', 2: 'New Line', 3: 'FSR 3.1', 4: '2x'}, 201: {5: 'A new help text.'}, 204: {6: 'Upscaler'}}

    def test_a_text_without_korean_stays_english_and_is_named(self):
        got, left = kpt.pc_settings(self.Menu)
        self.assertEqual(got, {200: {1: 'OFF', 2: 'New Line', 3: 'FSR 3.1', 4: '2x', **kpt.PC_MISSING},
                               201: {5: 'A new help text.'}, 204: {6: '업스케일러'}})
        self.assertEqual(left, ['A new help text.', 'New Line'], 'names and numbers are not left to translate')

    def test_the_real_texts_have_korean_every_one(self):
        pc_menu = kpt.lm.install_module(kpt.lm.INSTALL, 'pc_menu')
        got, left = kpt.pc_settings(pc_menu)
        self.assertEqual(left, [])
        english = {t for strings in pc_menu.texts().values() for t in strings.values()}
        self.assertEqual(sorted(set(kpt.PC_SETTINGS) - english), [], 'no Korean for a text bbport no longer has')
        want = {f: set(s) for f, s in pc_menu.texts().items()}
        want[200] |= set(kpt.PC_MISSING)
        self.assertEqual({f: set(s) for f, s in got.items()}, want)

    def test_every_label_the_menu_counts_has_a_text(self):
        # gpu/shim/bbport_pc_menu.cpp: UPSCALER_TEXT + u for u < UpscalerCount (7), FRAME_GEN_TEXT + f for
        # f < FrameGenCount (5), as bbport_settings.h has them in 1.9.7
        pc_menu = kpt.lm.install_module(kpt.lm.INSTALL, 'pc_menu')
        names = kpt.pc_settings(pc_menu)[0][200]
        self.assertEqual([sid for sid in [119100 + u for u in range(7)] + [119140 + f for f in range(5)]
                          if sid not in names], [])

    def test_a_label_bbport_has_itself_stays(self):
        class Menu:
            @staticmethod
            def texts():
                return {200: {119106: 'Its own'}}
        self.assertEqual(kpt.pc_settings(Menu, {})[0][200][119106], 'Its own')

    @unittest.skipUnless((kpt.lm.INSTALL / 'Game').is_dir(), 'needs the install')
    def test_the_translation_mods_font_has_every_character(self):
        pc_menu = kpt.lm.install_module(kpt.lm.INSTALL, 'pc_menu')
        s = kpt.lm.read_settings(kpt.lm.SETTINGS)
        mods = kpt.lm.folders(s, kpt.lm.INSTALL)['mods']
        font = kpt.font_characters((mods / kpt.SOURCE_MOD / 'dvdroot_ps4/menu/engus/font.gfx').read_bytes())
        self.assertGreater(len(font), 10000, 'the font was read')
        text = ''.join(t for strings in kpt.pc_settings(pc_menu)[0].values() for t in strings.values())
        text += ''.join(kpt.rebirth_texts(5)) + kpt.UNKNOWN + kpt.UNKNOWN_PLACE
        self.assertEqual(sorted(set(text) - font - {'\n'}), [])

    def test_font_characters_reads_a_code_table(self):
        def tag(code, body):
            return struct.pack('<HI', code << 6 | 0x3f, len(body)) + body

        def font(flags, offset_format, table, codes):
            # FontID, flags, language, name; the glyph count; two glyph offsets and the code table's offset
            # from the offset table's start; four bytes of shapes; the code table
            return (struct.pack('<HBBB', 1, flags, 0, 1) + b'x' + struct.pack('<H', 2)
                    + struct.pack(offset_format, 12, 14, table) + bytes(4) + codes)
        head = b'GFX\x0b' + bytes(4) + bytes([0]) + bytes(4)  # the stage rectangle with no bits, frame rate, count
        wide = font(0x8c, '<III', 16, struct.pack('<2H', 0xAC00, 0x41))
        narrow = font(0x00, '<HHH', 10, bytes([0x41, 0x42]))
        self.assertEqual(kpt.font_characters(head + tag(75, wide) + tag(0, b'')), {chr(0xAC00), 'A'})
        self.assertEqual(kpt.font_characters(head + tag(75, narrow) + tag(0, b'')), {'A', 'B'})
        with self.assertRaises(ValueError):
            kpt.font_characters(b'FWS' + bytes(20))


@unittest.skipUnless((kpt.lm.INSTALL / 'Game').is_dir(), 'needs the install')
class ChaliceParams(unittest.TestCase):
    """Every name and rite text the gravestone list can look up with the game's params, and with each
    mod's in the mods folder that the launcher would load (Vanilla Plus, bb_enhanced), has a text in the
    mods made now."""

    @classmethod
    def setUpClass(cls):
        cls.quit_menu = kpt.lm.install_module(kpt.lm.INSTALL, 'quit_menu')
        mods = kpt.lm.install_module(kpt.lm.INSTALL, 'mods')
        folders = kpt.lm.folders(kpt.lm.read_settings(kpt.lm.SETTINGS), kpt.lm.INSTALL)
        rel = 'dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx'
        cls.sources = [folders['game'] / rel]
        for name in mods.discover(folders['mods']):  # where the launcher's loader takes each mod's file from
            cls.sources += [source for path, source in mods.mod_files(folders['mods'] / name)
                            if Path(path).as_posix().casefold() == rel]
        cls.params = [chalice_rows(cls.quit_menu, p) for p in cls.sources]
        cls.made = kpt.mod_files(kpt.lm.INSTALL, kpt.lm.SETTINGS, say=lambda _l: None)

    def names_and_rites(self, params):
        """(name ids the list looks up, MenuText ids its rite slots look up, the feature name parts,
        the ids its main features string looks up)."""
        holy, features, lots = (params[n] for n in ROW_SIZES)
        field = lambda rows, at: {struct.unpack_from('<i', r, at)[0] for r in rows.values()}  # noqa: E731
        parts = {p for p in field(features, 0x1c) if p >= 0}
        names = {b + p for b in field(holy, 0x08) if b >= 0 for p in {0} | parts} - {0}  # 0 and below: no name
        rites = field(features, 0) | field(lots, 0) | {kpt.NO_NAME}  # a missing row reads 0
        main = {i for i in field(features, 0x20) if i > 0}  # through the text helper, which skips 0 and below
        return names, rites, parts, main

    def test_the_rite_parts_are_the_params(self):
        for source, params in zip(self.sources, self.params):
            names, _rites, parts, _main = self.names_and_rites(params)
            self.assertEqual(sorted({0} | parts), list(kpt.RITE_PARTS), source)
            self.assertIn(800000, names, 'the depth 8 row (6809)')
            self.assertEqual(len(names), 89, source)

    def test_every_name_has_a_text(self):
        for mod in (kpt.ITEM_MOD, kpt.VPLUS_MOD):
            for rel, data in self.made[mod].items():
                t = kpt.tables(self.quit_menu, data)
                for source, params in zip(self.sources, self.params):
                    names = self.names_and_rites(params)[0]
                    blank = sorted(i for i in names if t.get(120, {}).get(i) is None and t[19].get(i) is None)
                    self.assertEqual(blank, [], f'{mod} {rel} from {source}')
                self.assertEqual(t[19][800700], kpt.UNKNOWN_PLACE)
                self.assertIsNone(t[19].get(0), 'the list never looks up 0')

    def test_every_rite_has_a_text(self):
        for rel, data in self.made[kpt.OUT_MOD].items():
            menu = kpt.tables(self.quit_menu, data)[200]
            for source, params in zip(self.sources, self.params):
                _names, rites, _parts, main = self.names_and_rites(params)
                self.assertEqual(sorted(i for i in rites | main if menu.get(i) is None), [], f'{rel} from {source}')

    def test_the_menu_texts_are_stored_as_the_game_stores_them(self):
        for rel, data in self.made[kpt.OUT_MOD].items():
            bnd = self.quit_menu.unpack_dcx(data)
            fmg = next(bnd[o:o + n] for _e, o, n, fid in self.quit_menu.bnd4_files(bnd) if fid == kpt.MENU_FMG)
            count, = struct.unpack_from('<I', fmg, 0x10)
            at, = struct.unpack_from('<Q', fmg, 0x18)
            offsets = [o for o in struct.unpack_from(f'<{count}q', fmg, at) if o]
            self.assertEqual(len(offsets), len(set(offsets)), f'{rel}: no two entries share one copy')


if __name__ == '__main__':
    unittest.main(verbosity=2)
