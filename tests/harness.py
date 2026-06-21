# harness.py — host-side (CPython) test scaffolding.
#
# Importing this module:
#   * puts ../src on sys.path so `import leds` / `import patterns` work, and
#   * installs a fake `utime` module so device-only modules import on a PC.
#
# It also provides FakeStrip, a stand-in for a neopixel.NeoPixel buffer that
# records every pixel assignment so tests can assert what was rendered.

import os
import sys
import types

# Don't litter the source tree with __pycache__ when running tests on the host —
# those .pyc files are useless on the device and were getting deployed by flash.py.
sys.dont_write_bytecode = True

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


class _FakeUtime(types.ModuleType):
    """Minimal controllable stand-in for MicroPython's `utime`."""

    def __init__(self):
        super().__init__("utime")
        self._now = 0

    def ticks_ms(self):
        return self._now

    def ticks_diff(self, a, b):
        return a - b

    def sleep_ms(self, ms):
        self._now += ms

    # test helpers
    def set(self, ms):
        self._now = ms

    def advance(self, ms):
        self._now += ms


fake_utime = _FakeUtime()
sys.modules["utime"] = fake_utime


class FakeStrip:
    """List-like stand-in for neopixel.NeoPixel; records pixel writes."""

    def __init__(self, n):
        self.buf = [(0, 0, 0)] * n
        self.writes = 0

    def __len__(self):
        return len(self.buf)

    def __getitem__(self, i):
        return self.buf[i]

    def __setitem__(self, i, value):
        self.buf[i] = value

    def fill(self, value):
        for i in range(len(self.buf)):
            self.buf[i] = value

    def write(self):
        self.writes += 1
