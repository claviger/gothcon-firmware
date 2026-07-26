# buttons.py — GPIO interrupt-driven button handler with debounce
#
# The badge has four directional pushbuttons (silkscreen S4-S7), all active-low
# with internal pull-ups enabled (unpressed = HIGH, pressed = LOW):
#
#   Up    = S6 = IO4      Down  = S7 = IO3
#   Left  = S4 = IO0      Right = S5 = IO2
#
# The badge's BOOT (S3) and RESET (S2) buttons are separate hardware controls
# wired to the chip's strapping/enable circuitry — they are NOT on these GPIOs
# and are not handled here.
#
# Uses micropython.schedule() to dispatch user callbacks outside hard-ISR
# context, where heap allocation is safe.

import micropython
import utime
from machine import Pin

DEBOUNCE_MS = 50

# Badge button map: name -> GPIO (silkscreen labels in comments)
PIN_UP    = 4   # S6
PIN_DOWN  = 3   # S7
PIN_LEFT  = 0   # S4
PIN_RIGHT = 2   # S5

# Keyed by integer GPIO number
_callbacks  = {}   # pin_num -> callable(pin_num)
_last_event = {}   # pin_num -> ticks_ms of last accepted press
_pins       = {}   # pin_num -> Pin object (kept alive to prevent GC)


def _make_isr(pin_num):
    """Return a hard ISR closure with pin_num captured at registration time."""
    def _isr(pin):
        now  = utime.ticks_ms()
        last = _last_event.get(pin_num, -DEBOUNCE_MS - 1)
        if utime.ticks_diff(now, last) < DEBOUNCE_MS:
            return  # within debounce window — discard
        _last_event[pin_num] = now
        micropython.schedule(_dispatch, pin_num)
    return _isr


def _dispatch(pin_num):
    """Soft callback — runs outside ISR context; heap allocation is safe."""
    cb = _callbacks.get(pin_num)
    if cb:
        cb(pin_num)


def register(pin_num: int, callback) -> None:
    """
    Register a callback for a single button GPIO.

    Args:
        pin_num:  GPIO number (see PIN_UP/PIN_DOWN/PIN_LEFT/PIN_RIGHT)
        callback: callable(pin_num) invoked on each debounced button press
    """
    p = Pin(pin_num, Pin.IN, Pin.PULL_UP)
    _pins[pin_num]       = p            # prevent garbage collection
    _callbacks[pin_num]  = callback
    _last_event[pin_num] = utime.ticks_ms()
    p.irq(trigger=Pin.IRQ_FALLING, handler=_make_isr(pin_num))


def register_all(cb_up, cb_down, cb_left, cb_right) -> None:
    """
    Register callbacks for all four directional buttons in one call.

    Args:
        cb_up:    callback for Up    (S6, IO4)
        cb_down:  callback for Down  (S7, IO3)
        cb_left:  callback for Left  (S4, IO0)
        cb_right: callback for Right (S5, IO2)
    """
    register(PIN_UP,    cb_up)
    register(PIN_DOWN,  cb_down)
    register(PIN_LEFT,  cb_left)
    register(PIN_RIGHT, cb_right)


def is_pressed(pin_num: int) -> bool:
    """True while the button is held down right now (active-low: pin reads 0).

    Complements the edge-triggered callbacks — lets the main loop poll for
    hold/release (e.g. the 5s wireless opt-out hold). False for pins that
    were never registered.
    """
    p = _pins.get(pin_num)
    return p is not None and p.value() == 0


def unregister(pin_num: int) -> None:
    """Detach the IRQ and remove the callback for a button."""
    p = _pins.pop(pin_num, None)
    if p:
        p.irq(handler=None)
    _callbacks.pop(pin_num, None)
    _last_event.pop(pin_num, None)
