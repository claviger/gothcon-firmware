# test_leds.py — layout constants and body/eye helpers.

import unittest

import harness  # noqa: F401  (sets sys.path, installs fake utime)
from harness import FakeStrip
import leds


class TestLayout(unittest.TestCase):
    def test_num_leds_is_44(self):
        self.assertEqual(leds.NUM_LEDS, 44)

    def test_eyes_are_32_and_36(self):
        self.assertEqual(leds.EYES, (32, 36))

    def test_body_excludes_eyes(self):
        self.assertNotIn(32, leds.BODY)
        self.assertNotIn(36, leds.BODY)

    def test_body_has_42_pixels_in_order(self):
        self.assertEqual(len(leds.BODY), 42)
        self.assertEqual(list(leds.BODY), sorted(leds.BODY))


class TestHelpers(unittest.TestCase):
    def setUp(self):
        leds._np = FakeStrip(leds.NUM_LEDS)

    def test_set_eyes_sets_only_eye_pixels(self):
        leds.set_eyes(10, 10, 10)
        white = (leds._scale(10), leds._scale(10), leds._scale(10))
        self.assertEqual(leds._np[32], white)
        self.assertEqual(leds._np[36], white)
        self.assertEqual(leds._np[0], (0, 0, 0))   # body untouched

    def test_set_body_all_fills_body_but_not_eyes(self):
        leds.set_body_all(10, 0, 0)
        red = (leds._scale(10), 0, 0)
        self.assertEqual(leds._np[0], red)
        self.assertEqual(leds._np[31], red)
        self.assertEqual(leds._np[33], red)
        self.assertEqual(leds._np[32], (0, 0, 0))   # eye untouched
        self.assertEqual(leds._np[36], (0, 0, 0))   # eye untouched

    def test_set_body_logical_skips_over_eyes(self):
        # logical body position 32 maps past the first eye (phys 32) to phys 33
        self.assertEqual(leds.BODY[32], 33)
        leds.set_body_logical(32, 0, 10, 0)
        green = (0, leds._scale(10), 0)
        self.assertEqual(leds._np[33], green)

    def test_clear_body_zeros_body_only(self):
        leds.set_eyes(10, 10, 10)
        leds.set_body_all(10, 0, 0)
        leds.clear_body()
        self.assertEqual(leds._np[0], (0, 0, 0))
        white = (leds._scale(10), leds._scale(10), leds._scale(10))
        self.assertEqual(leds._np[32], white)   # eyes survive


if __name__ == "__main__":
    unittest.main()
