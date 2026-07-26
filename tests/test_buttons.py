# test_buttons.py — named button map and IRQ/debounce dispatch.

import unittest

import harness  # noqa: F401  (sets sys.path, installs fake utime/machine/micropython)
from harness import FakePin, fake_utime
import buttons


class TestPinMap(unittest.TestCase):
    def test_named_pins_match_badge_silkscreen(self):
        self.assertEqual(buttons.PIN_UP, 4)     # S6
        self.assertEqual(buttons.PIN_DOWN, 3)   # S7
        self.assertEqual(buttons.PIN_LEFT, 0)   # S4
        self.assertEqual(buttons.PIN_RIGHT, 2)  # S5

    def test_named_pins_are_distinct(self):
        pins = {buttons.PIN_UP, buttons.PIN_DOWN, buttons.PIN_LEFT,
                buttons.PIN_RIGHT}
        self.assertEqual(len(pins), 4)


class TestRegisterAll(unittest.TestCase):
    def setUp(self):
        FakePin.instances.clear()
        buttons._callbacks.clear()
        buttons._last_event.clear()
        buttons._pins.clear()
        self.presses = []
        buttons.register_all(
            lambda p: self.presses.append(("up", p)),
            lambda p: self.presses.append(("down", p)),
            lambda p: self.presses.append(("left", p)),
            lambda p: self.presses.append(("right", p)),
        )

    def test_configures_pullup_input_with_falling_irq(self):
        for pin_num in (buttons.PIN_UP, buttons.PIN_DOWN,
                        buttons.PIN_LEFT, buttons.PIN_RIGHT):
            pin = FakePin.instances[pin_num]
            self.assertEqual(pin.mode, FakePin.IN)
            self.assertEqual(pin.pull, FakePin.PULL_UP)
            self.assertEqual(pin.trigger, FakePin.IRQ_FALLING)
            self.assertIsNotNone(pin.handler)

    def test_press_dispatches_the_named_callback(self):
        fake_utime.advance(100)      # clear the registration debounce window
        FakePin.instances[buttons.PIN_UP].press()
        self.assertEqual(self.presses, [("up", buttons.PIN_UP)])

    def test_bounce_within_debounce_window_is_discarded(self):
        fake_utime.advance(100)
        FakePin.instances[buttons.PIN_LEFT].press()
        fake_utime.advance(buttons.DEBOUNCE_MS - 1)
        FakePin.instances[buttons.PIN_LEFT].press()   # bounce — ignored
        fake_utime.advance(buttons.DEBOUNCE_MS + 1)
        FakePin.instances[buttons.PIN_LEFT].press()   # genuine second press
        self.assertEqual([name for name, _ in self.presses], ["left", "left"])

    def test_press_at_exact_debounce_boundary_is_accepted(self):
        fake_utime.advance(100)
        FakePin.instances[buttons.PIN_LEFT].press()
        fake_utime.advance(buttons.DEBOUNCE_MS)   # exactly the boundary — accepted
        FakePin.instances[buttons.PIN_LEFT].press()
        self.assertEqual([name for name, _ in self.presses], ["left", "left"])

    def test_unregister_stops_dispatch_for_that_pin_only(self):
        fake_utime.advance(100)
        buttons.unregister(buttons.PIN_UP)
        FakePin.instances[buttons.PIN_UP].press()      # no-op after unregister
        FakePin.instances[buttons.PIN_RIGHT].press()   # still works
        self.assertEqual(self.presses, [("right", buttons.PIN_RIGHT)])

    def test_is_pressed_reflects_active_low_pin_level(self):
        fake_utime.advance(100)
        self.assertFalse(buttons.is_pressed(buttons.PIN_DOWN))   # idle = high
        FakePin.instances[buttons.PIN_DOWN].hold()               # held low
        self.assertTrue(buttons.is_pressed(buttons.PIN_DOWN))
        FakePin.instances[buttons.PIN_DOWN].release()
        self.assertFalse(buttons.is_pressed(buttons.PIN_DOWN))

    def test_is_pressed_false_for_unregistered_pin(self):
        self.assertFalse(buttons.is_pressed(99))


if __name__ == "__main__":
    unittest.main()
