# test_leds.py — layout constants and body/eye helpers.

import unittest

import harness  # noqa: F401  (sets sys.path, installs fake utime)
from harness import FakeStrip
import leds


class TestLayout(unittest.TestCase):
    def test_num_leds_is_44(self):
        self.assertEqual(leds.NUM_LEDS, 44)

    def test_eyes_are_28_and_30(self):
        # Physical eye indices identified on the badge with the diagnostic sweep.
        self.assertEqual(leds.EYES, (28, 30))

    def test_body_excludes_eyes(self):
        for eye in leds.EYES:
            self.assertNotIn(eye, leds.BODY)

    def test_body_is_everything_but_the_eyes_in_order(self):
        self.assertEqual(len(leds.BODY), leds.NUM_LEDS - len(leds.EYES))
        self.assertEqual(len(leds.BODY), 42)
        self.assertEqual(list(leds.BODY), sorted(leds.BODY))


class TestHelpers(unittest.TestCase):
    def setUp(self):
        leds._np = FakeStrip(leds.NUM_LEDS)

    def test_set_eyes_sets_only_eye_pixels(self):
        leds.set_eyes(10, 10, 10)
        white = (leds._scale(10), leds._scale(10), leds._scale(10))
        for eye in leds.EYES:
            self.assertEqual(leds._np[eye], white)
        self.assertEqual(leds._np[leds.BODY[0]], (0, 0, 0))   # body untouched

    def test_set_body_all_fills_body_but_not_eyes(self):
        leds.set_body_all(10, 0, 0)
        red = (leds._scale(10), 0, 0)
        for i in leds.BODY:
            self.assertEqual(leds._np[i], red)
        for eye in leds.EYES:
            self.assertEqual(leds._np[eye], (0, 0, 0))

    def test_set_body_logical_never_writes_to_an_eye(self):
        # Painting every logical body position fills the body and leaves the
        # eyes dark — i.e. logical positions map past the eye indices.
        for pos in range(leds.BODY_COUNT):
            leds.set_body_logical(pos, 10, 0, 0)
        red = (leds._scale(10), 0, 0)
        for i in leds.BODY:
            self.assertEqual(leds._np[i], red)
        for eye in leds.EYES:
            self.assertEqual(leds._np[eye], (0, 0, 0))

    def test_set_body_logical_maps_to_body_index(self):
        leds.set_body_logical(5, 0, 10, 0)
        green = (0, leds._scale(10), 0)
        self.assertEqual(leds._np[leds.BODY[5]], green)

    def test_clear_body_zeros_body_only(self):
        leds.set_eyes(10, 10, 10)
        leds.set_body_all(10, 0, 0)
        leds.clear_body()
        self.assertEqual(leds._np[leds.BODY[0]], (0, 0, 0))
        white = (leds._scale(10), leds._scale(10), leds._scale(10))
        for eye in leds.EYES:
            self.assertEqual(leds._np[eye], white)   # eyes survive


if __name__ == "__main__":
    unittest.main()
