"""Game-free checks of make_game's other builds (OTHER_BUILDS): taken by the check, the unpack and a kept exefs, and said as
not yet played; a build in neither list is still refused with the same words.

Run with: python -I tests/test_make_game_other_builds.py
"""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "nx2" / "make_game.py"
spec = importlib.util.spec_from_file_location("make_game_other_builds", SOURCE)
make_game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_game)


def exefs_with(folder, build):
    """An authored exefs: a main whose header holds the build id's first bytes, nothing of a game"""
    os.makedirs(folder, exist_ok=True)
    header = bytearray(0x60)
    header[:4] = b"NSO0"
    header[0x40:0x44] = bytes.fromhex(build)
    with open(os.path.join(folder, "main"), "wb") as f:
        f.write(bytes(header) + b"authored")
    return folder


class OtherBuilds(unittest.TestCase):
    def test_lists(self):
        self.assertIn("a6ce40dc", make_game.OTHER_BUILDS)
        self.assertNotIn(make_game.BUILD_ID, make_game.OTHER_BUILDS)
        for b in make_game.OTHER_BUILDS:
            self.assertRegex(b, r"^[0-9a-f]{8,40}$")

    def test_supported_build(self):
        self.assertTrue(make_game.supported_build(make_game.BUILD_ID + "00" * 16))
        self.assertTrue(make_game.supported_build("a6ce40dc" + "00" * 16))
        self.assertTrue(make_game.supported_build("A6CE40DC" + "00" * 16))
        self.assertFalse(make_game.supported_build("01234567" + "00" * 16))
        self.assertFalse(make_game.supported_build(""))

    def test_unpack_and_kept_exefs(self):
        with tempfile.TemporaryDirectory() as d:
            for build, ok in ((make_game.BUILD_ID, True), ("a6ce40dc", True), ("01234567", False)):
                with self.subTest(build=build):
                    exefs = exefs_with(os.path.join(d, build), build)
                    self.assertEqual(make_game.exefs_problem(exefs), None if ok else "another build of the game")
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                        if ok:
                            make_game.check_supported_build(exefs)
                        else:
                            with self.assertRaises(SystemExit):
                                make_game.check_supported_build(exefs)
                    if not ok:
                        self.assertIn("This is build 01234567. Inhale supports build %s." % make_game.BUILD_ID, out.getvalue())

    def test_check_says_not_yet_played(self):
        with tempfile.TemporaryDirectory() as d:
            said = []
            with mock.patch.object(make_game, "check_windows_sdk", lambda work: None), \
                    mock.patch.object(make_game, "say", lambda *w: said.append(w)):
                for build in (make_game.BUILD_ID, "a6ce40dc", "01234567"):
                    make_game.check(SimpleNamespace(nup=None, exefs=exefs_with(os.path.join(d, build), build)), d)
        self.assertEqual([w[1] for w in said], ["ok", "ok", "bad"])
        self.assertIn("the version Inhale supports", said[0][2])
        self.assertIn("This is build a6ce40dc: Inhale builds it, but it has not been played yet.", said[1][2])
        self.assertEqual(said[2][2], "This is build 01234567. Inhale supports build %s." % make_game.BUILD_ID)


if __name__ == "__main__":
    unittest.main()
