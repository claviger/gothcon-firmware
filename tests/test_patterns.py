# test_patterns.py — two-axis pattern/palette API and per-pattern behavior.

import random
import unittest

import harness  # noqa: F401  (sets sys.path, installs fake utime)
from harness import FakeStrip
import leds
import patterns

# Pattern indices (per spec order).
# TEST_PATTERN is a TEMPORARY diagnostic stub at index 0 (power-on default) used
# to identify the physical eye indices; remove it (and shift back to range(6))
# once the correct eye LEDs are known.
TEST_PATTERN, SOLID, CHASE, TWINKLE, WASH, SWAP, BREATHE = range(7)


def scaled(c):
    return (leds._scale(c[0]), leds._scale(c[1]), leds._scale(c[2]))


WHITE = None  # set after import; eyes default colour


class _Base(unittest.TestCase):
    def setUp(self):
        leds._np = FakeStrip(leds.NUM_LEDS)

    def body(self, pos):
        return leds._np[leds.BODY[pos]]

    def assert_eyes_white(self):
        for eye in leds.EYES:
            r, g, b = leds._np[eye]
            self.assertEqual(r, g)
            self.assertEqual(g, b)   # equal channels == a shade of white


class TestApi(_Base):
    def test_pattern_count_and_names(self):
        self.assertEqual(patterns.pattern_count(), 7)   # 6 + TEMP test pattern
        self.assertEqual(patterns.pattern_name(TEST_PATTERN), "test pattern")
        self.assertEqual(patterns.pattern_name(SOLID), "solid")
        self.assertEqual(patterns.pattern_name(BREATHE), "breathe")

    def test_palette_count_and_names(self):
        self.assertEqual(patterns.palette_count(), 6)
        self.assertEqual(patterns.palette_name(0), "rainbow")

    def test_palette_change_recolors_body(self):
        patterns.activate(SOLID, 0)            # rainbow[0]
        first = self.body(0)
        patterns.activate(SOLID, 3)            # ghost[0]
        second = self.body(0)
        self.assertNotEqual(first, second)
        self.assertEqual(second, scaled(patterns.PALETTES[3]["colors"][0]))


class TestSolid(_Base):
    def test_fills_body_with_first_color_eyes_white(self):
        patterns.activate(SOLID, 0)
        exp = scaled(patterns.PALETTES[0]["colors"][0])
        for pos in range(leds.BODY_COUNT):
            self.assertEqual(self.body(pos), exp)
        self.assert_eyes_white()

    def test_is_static(self):
        patterns.activate(SOLID, 0)
        before = list(leds._np.buf)
        patterns.tick(SOLID, 0, 99999)        # no-op for static pattern
        self.assertEqual(leds._np.buf, before)


class TestChase(_Base):
    def test_initial_render_offset_zero(self):
        patterns.activate(CHASE, 1)
        colors = patterns.PALETTES[1]["colors"]
        n = len(colors)
        for pos in range(leds.BODY_COUNT):
            self.assertEqual(self.body(pos), scaled(colors[pos % n]))
        self.assert_eyes_white()

    def test_advances_one_step_after_step_ms(self):
        patterns.activate(CHASE, 1)
        colors = patterns.PALETTES[1]["colors"]
        n = len(colors)
        patterns.tick(CHASE, 1, 0)                    # init last_ms
        patterns.tick(CHASE, 1, patterns.CHASE_STEP_MS)
        for pos in range(leds.BODY_COUNT):
            self.assertEqual(self.body(pos), scaled(colors[(pos + 1) % n]))


class TestWash(_Base):
    def test_floods_then_advances_palette(self):
        patterns.activate(WASH, 2)                    # ember
        colors = patterns.PALETTES[2]["colors"]
        t = 0
        patterns.tick(WASH, 2, t)                     # init last_ms
        for _ in range(leds.BODY_COUNT):
            t += patterns.WASH_STEP_MS
            patterns.tick(WASH, 2, t)
        for pos in range(leds.BODY_COUNT):            # whole body now color[0]
            self.assertEqual(self.body(pos), scaled(colors[0]))
        t += patterns.WASH_STEP_MS
        patterns.tick(WASH, 2, t)                     # next color starts washing
        self.assertEqual(self.body(0), scaled(colors[1]))
        self.assert_eyes_white()


class TestSwap(_Base):
    def test_block_colors_rotate(self):
        patterns.activate(SWAP, 1)                    # rip, 3 colors
        colors = patterns.PALETTES[1]["colors"]
        n = len(colors)
        self.assertEqual(self.body(0), scaled(colors[0]))
        patterns.tick(SWAP, 1, 0)                     # init last_ms
        patterns.tick(SWAP, 1, patterns.SWAP_STEP_MS)
        self.assertEqual(self.body(0), scaled(colors[1 % n]))


class TestBreathe(_Base):
    def test_eyes_counter_pulse_body(self):
        patterns.activate(BREATHE, 2)
        samples = []
        t = 0
        patterns.tick(BREATHE, 2, t)                  # init last_ms
        for _ in range(120):
            t += patterns.BREATHE_STEP_MS
            patterns.tick(BREATHE, 2, t)
            body_sum = sum(self.body(0))
            eye_sum = sum(leds._np[leds.EYES[0]])
            samples.append((body_sum, eye_sum))
        dim_body = min(samples, key=lambda s: s[0])
        bright_body = max(samples, key=lambda s: s[0])
        # eyes brightest when body dimmest (counter-pulse)
        self.assertGreater(dim_body[1], bright_body[1])


class TestTwinkle(_Base):
    def test_majority_off_but_some_lit(self):
        random.seed(1234)
        patterns.activate(TWINKLE, 0)
        lit_counts = []
        t = 0
        patterns.tick(TWINKLE, 0, t)                  # init last_ms
        for _ in range(60):
            t += patterns.TWINKLE_STEP_MS
            patterns.tick(TWINKLE, 0, t)
            lit = sum(1 for pos in range(leds.BODY_COUNT)
                      if self.body(pos) != (0, 0, 0))
            lit_counts.append(lit)
        self.assertGreaterEqual(max(lit_counts), 1)                    # something twinkles
        self.assertLessEqual(max(lit_counts), int(leds.BODY_COUNT * 0.4))  # majority off


class TestTestPattern(_Base):
    """TEMP diagnostic stub — lights each physical LED (1..44) white in turn."""

    def test_lights_first_physical_led_only(self):
        patterns.activate(TEST_PATTERN, 0)
        white = scaled((10, 10, 10))
        self.assertEqual(leds._np[0], white)
        for i in range(1, leds.NUM_LEDS):
            self.assertEqual(leds._np[i], (0, 0, 0))

    def test_advances_one_physical_led_per_step(self):
        patterns.activate(TEST_PATTERN, 0)
        white = scaled((10, 10, 10))
        patterns.tick(TEST_PATTERN, 0, 0)                    # init last_ms
        patterns.tick(TEST_PATTERN, 0, patterns.TEST_STEP_MS)
        self.assertEqual(leds._np[1], white)
        self.assertEqual(leds._np[0], (0, 0, 0))

    def test_covers_every_physical_index_including_eyes_then_wraps(self):
        patterns.activate(TEST_PATTERN, 0)
        white = scaled((10, 10, 10))
        lit_order = [0]
        t = 0
        patterns.tick(TEST_PATTERN, 0, t)                    # init last_ms
        for _ in range(leds.NUM_LEDS):
            t += patterns.TEST_STEP_MS
            patterns.tick(TEST_PATTERN, 0, t)
            lit = [i for i in range(leds.NUM_LEDS) if leds._np[i] == white]
            self.assertEqual(len(lit), 1)                    # exactly one lit
            lit_order.append(lit[0])
        # every physical index 0..43 was lit (the eyes are addressed too)
        self.assertEqual(set(lit_order[:leds.NUM_LEDS]), set(range(leds.NUM_LEDS)))
        self.assertEqual(lit_order[leds.NUM_LEDS], 0)        # wrapped back to start


class TestEyesContract(_Base):
    def test_all_patterns_keep_eyes_white(self):
        for pi in range(patterns.pattern_count()):
            leds._np = FakeStrip(leds.NUM_LEDS)
            patterns.activate(pi, 0)
            t = 0
            for _ in range(10):
                t += 100
                patterns.tick(pi, 0, t)
            for eye in leds.EYES:
                r, g, b = leds._np[eye]
                self.assertEqual(r, g)
                self.assertEqual(g, b)


if __name__ == "__main__":
    unittest.main()
