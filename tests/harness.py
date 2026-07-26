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


class FakePin:
    """Stand-in for machine.Pin; records config and lets tests fire the IRQ."""

    IN          = "IN"
    OUT         = "OUT"
    PULL_UP     = "PULL_UP"
    IRQ_FALLING = "IRQ_FALLING"
    IRQ_RISING  = "IRQ_RISING"

    instances = {}   # pin_num -> most recently constructed FakePin

    def __init__(self, pin_num, mode=None, pull=None):
        self.pin_num = pin_num
        self.mode    = mode
        self.pull    = pull
        self.trigger = None
        self.handler = None
        self._value  = 1          # active-low buttons idle HIGH
        FakePin.instances[pin_num] = self

    def irq(self, trigger=None, handler=None):
        self.trigger = trigger
        self.handler = handler

    def value(self):
        return self._value

    def press(self):
        """Test helper: simulate the falling-edge interrupt firing."""
        if self.handler:
            self.handler(self)

    def hold(self):
        """Test helper: press AND keep the pin low (button held down)."""
        self._value = 0
        self.press()

    def release(self):
        """Test helper: let the pin float back high (button released)."""
        self._value = 1


_fake_machine = types.ModuleType("machine")
_fake_machine.Pin = FakePin
sys.modules["machine"] = _fake_machine

# micropython.schedule() defers a soft callback; on the host, run it immediately.
_fake_micropython = types.ModuleType("micropython")
_fake_micropython.schedule = lambda fn, arg: fn(arg)
sys.modules["micropython"] = _fake_micropython


class FakeWLAN:
    """Stand-in for network.WLAN(network.STA_IF); records activity."""

    MAC = b"\x02\x11\x22\x33\x44\x55"

    def __init__(self, interface):
        self.interface   = interface
        self.is_active   = False
        self.call_log    = []     # ("active", v) / ("config", kwargs) / ("disconnect",)
        self.channel     = None
        FakeWLAN.last = self      # class attr: most recent instance for assertions

    def active(self, v=None):
        if v is None:
            return self.is_active
        self.is_active = bool(v)
        self.call_log.append(("active", bool(v)))
        return self.is_active

    def config(self, key=None, **kwargs):
        if key == "mac":
            return self.MAC
        if kwargs:
            self.call_log.append(("config", kwargs))
            if "channel" in kwargs:
                self.channel = kwargs["channel"]

    def disconnect(self):
        self.call_log.append(("disconnect",))


_fake_network = types.ModuleType("network")
_fake_network.STA_IF = 0
_fake_network.AP_IF = 1
_fake_network.WLAN = FakeWLAN
sys.modules["network"] = _fake_network


class FakeESPNow:
    """Stand-in for espnow.ESPNow(); tests feed rx_queue and inspect sent."""

    def __init__(self):
        self.is_active = False
        self.peers     = []
        self.sent      = []       # list of (peer_mac, payload_bytes)
        self.rx_queue  = []       # tests append (sender_mac, payload_bytes)
        FakeESPNow.last = self    # class attr: most recent instance for assertions

    def active(self, v=None):
        if v is None:
            return self.is_active
        self.is_active = bool(v)
        return self.is_active

    def add_peer(self, mac):
        if mac not in self.peers:
            self.peers.append(mac)

    def send(self, peer, msg, sync=True):
        self.sent.append((bytes(peer), bytes(msg)))
        return True

    def any(self):
        return len(self.rx_queue) > 0

    def recv(self, timeout_ms=None):
        if self.rx_queue:
            mac, msg = self.rx_queue.pop(0)
            return [mac, msg]
        return [None, None]


_fake_espnow = types.ModuleType("espnow")
_fake_espnow.ESPNow = FakeESPNow
sys.modules["espnow"] = _fake_espnow
