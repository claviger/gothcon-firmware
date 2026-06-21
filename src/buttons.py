# buttons.py — GPIO interrupt-driven button handler with debounce
#
# Registers IRQ handlers for active-low pushbuttons on IO0, IO2, IO3, IO4.
# Uses micropython.schedule() to dispatch user callbacks outside hard-ISR
# context, where heap allocation is safe.
#
# Wiring assumption: buttons pull the GPIO pin to GND when pressed.
# Internal PULL_UP resistors are enabled so unpressed = HIGH, pressed = LOW.
#
# IO0 note: This is the BOOT button on most ESP32-C3 boards. Holding it LOW
# at power-on forces ROM bootloader mode. At runtime it is a normal GPIO.

import micropython
import utime
from machine import Pin

DEBOUNCE_MS = 50

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
        pin_num:  GPIO number (e.g. 0, 2, 3, 4)
        callback: callable(pin_num) invoked on each debounced button press
    """
    p = Pin(pin_num, Pin.IN, Pin.PULL_UP)
    _pins[pin_num]       = p            # prevent garbage collection
    _callbacks[pin_num]  = callback
    _last_event[pin_num] = utime.ticks_ms()
    p.irq(trigger=Pin.IRQ_FALLING, handler=_make_isr(pin_num))


def register_all(cb_io0, cb_io2, cb_io3, cb_io4) -> None:
    """
    Register callbacks for all four buttons in one call.

    Args:
        cb_io0: callback for IO0 (BOOT button)
        cb_io2: callback for IO2
        cb_io3: callback for IO3
        cb_io4: callback for IO4
    """
    register(0, cb_io0)
    register(2, cb_io2)
    register(3, cb_io3)
    register(4, cb_io4)


def unregister(pin_num: int) -> None:
    """Detach the IRQ and remove the callback for a button."""
    p = _pins.pop(pin_num, None)
    if p:
        p.irq(handler=None)
    _callbacks.pop(pin_num, None)
    _last_event.pop(pin_num, None)
