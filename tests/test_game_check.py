from paths import ROOT
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import game_check
from test_prepare import fixture


def param_sfo(entries):
    """A minimal param.sfo with UTF-8 string entries."""
    keys = b''.join(k.encode() + b'\0' for k in entries)
    values = [v.encode() + b'\0' for v in entries.values()]
    count = len(entries)
    key_table = 20 + 16 * count
    data_table = key_table + len(keys)
    data = bytearray(struct.pack('<4sIIII', b'\0PSF', 0x101, key_table, data_table, count))
    key_off = data_off = 0
    for key, value in zip(entries, values):
        data += struct.pack('<HHIII', key_off, 0x204, len(value), len(value), data_off)
        key_off += len(key) + 1
        data_off += len(value)
    return bytes(data + keys + b''.join(values))


class GameCheckTests(unittest.TestCase):
    def game(self, title, version, eboot=None):
        path = Path(self.tmp.name)
        (path / 'sce_sys').mkdir(exist_ok=True)
        (path / 'sce_sys/param.sfo').write_bytes(param_sfo({'APP_VER': version, 'TITLE_ID': title}))
        (path / 'eboot.bin').write_bytes(fixture() if eboot is None else eboot)
        return path

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ.pop('BB_SKIP_GAME_CHECK', None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_base_game_without_the_update(self):
        game = self.game('CUSA14209', '01.00')
        self.assertEqual(game_check.problem(game), ('missing_update', 'CUSA14209', '01.00'))
        self.assertIn('28.00', game_check.explain(*game_check.problem(game)))

    def test_older_update_is_a_missing_update(self):
        game = self.game('CUSA14204', '27.00')
        self.assertEqual(game_check.problem(game), ('missing_update', 'CUSA14204', '27.00'))

    def test_update_metadata_with_an_old_executable(self):
        game = self.game('CUSA14209', '28.00')
        with mock.patch.dict(game_check.OLD_IMAGES, {game_check.image_sha256(game): '01.00'}):
            self.assertEqual(game_check.problem(game)[0], 'wrong_eboot')
            self.assertIsNone(game_check.profile(game))

    def test_unrecorded_2800_build_is_accepted_as_unmapped(self):
        # Bring-up: a 28.00 executable whose image hash is not in SUPPORTED yet runs, with the
        # address-keyed diagnostics off (the variant is not the reference build).
        for title in ('CUSA14209', 'CUSA14204'):
            game = self.game(title, '28.00')
            self.assertIsNone(game_check.problem(game))
            p = game_check.profile(game)
            self.assertEqual(p['name'], 'ufc4')
            self.assertEqual(p['title'], title)
            self.assertEqual(p['variant'], 'unmapped')
            self.assertNotEqual(p['variant'], '5.05')
            self.assertFalse(p['known'])

    def test_other_title(self):
        # UFC 3 (the port this one is built from) and Bloodborne are not profiles here.
        self.assertEqual(game_check.problem(self.game('CUSA06534', '01.14'))[0], 'other_title')
        self.assertEqual(game_check.problem(self.game('CUSA03173', '01.09'))[0], 'other_title')
        self.assertIn('CUSA14209', game_check.explain(*game_check.problem(self.game('CUSA06534', '01.14'))))

    def test_unreadable_executable(self):
        self.assertEqual(game_check.problem(self.game('CUSA14209', '28.00', b'junk'))[0], 'unreadable')

    def test_recorded_image_is_pinned(self):
        game = self.game('CUSA14204', '28.00')
        with mock.patch.object(game_check, 'SUPPORTED', {game_check.image_sha256(game): 'CUSA14204'}):
            self.assertIsNone(game_check.problem(game))
            p = game_check.profile(game)
            self.assertEqual(p['name'], 'ufc4')
            self.assertEqual(p['title'], 'CUSA14204')
            self.assertEqual(p['variant'], 'pinned')
            self.assertEqual(p['modules'], ('libc.prx', 'libSceFios2.prx'))

    def test_profile_guess_with_the_check_skipped(self):
        game = self.game('CUSA14209', '01.00')
        self.assertIsNone(game_check.profile(game))
        with mock.patch.dict(os.environ, {'BB_SKIP_GAME_CHECK': '1'}):
            self.assertEqual(game_check.profile(game)['name'], 'ufc4')
            self.assertEqual(game_check.profile(game)['variant'], '?')
            self.assertIsNone(game_check.profile(self.game('CUSA03173', '01.09')))

    def test_skip_switch(self):
        os.environ['BB_SKIP_GAME_CHECK'] = '1'
        self.assertIsNone(game_check.problem(self.game('CUSA14209', '01.00')))

    def test_every_problem_is_explained(self):
        for kind in ('missing_update', 'wrong_eboot', 'other_title', 'unreadable'):
            self.assertIn('CUSA', game_check.explain(kind, 'CUSA14209', '01.00'))
            self.assertIn('CUSA', game_check.explain(kind, 'CUSA00000', '01.00'))


if __name__ == '__main__':
    unittest.main()
