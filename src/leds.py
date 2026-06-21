# leds.py — WS2812B (NeoPixel) driver wrapper
#
# Controls a strip of 40 addressable RGB LEDs daisy-chained on IO10.
# Uses MicroPython's built-in `neopixel` module (no extra install required).
#
# POWER WARNING:
#   40 WS2812Bs at full white (255, 255, 255) draw ~2.4A @ 5V.
#   The ESP32-C3's onboard 3.3V regulator cannot supply this.
#   Feed the LED strip VDD from a dedicated 5V supply; share GND with the MCU.
#   For USB-powered prototyping keep per-channel values ≤ 64 (~520mA total).
#
# TIMING WARNING:
#   np.write() is a blocking call (~52ms for 40 LEDs). Do not call from an ISR.

import neopixel
from machine import Pin

NUM_LEDS = 44
LED_PIN  = 10

# Global brightness limiter: maximum raw neopixel value (0–255) that a
# logical brightness of 10 maps to.  Default is 3 to conserve power. 
# Values above 10 may cause the MCU to lock up due to voltage drop.
BRIGHTNESS = 20

_np: neopixel.NeoPixel = None  # type: ignore


def _scale(v: int) -> int:
    """Map a logical brightness (0–10) to a raw neopixel value (0–255)."""
    return round(v * BRIGHTNESS / 10)


def init() -> None:
    """Initialise the NeoPixel strip. Must be called before any other function."""
    global _np
    _np = neopixel.NeoPixel(Pin(LED_PIN, Pin.OUT), NUM_LEDS)
    clear()
    write()


def set_all(r: int, g: int, b: int) -> None:
    """Fill every LED with the same colour (0–10 scale). Call write() to push to hardware."""
    _np.fill((_scale(r), _scale(g), _scale(b)))


def set_one(index: int, r: int, g: int, b: int) -> None:
    """Set a single LED by index (0-based, 0–10 scale). Call write() to push to hardware."""
    if 0 <= index < NUM_LEDS:
        _np[index] = (_scale(r), _scale(g), _scale(b))


def set_range(start: int, end: int, r: int, g: int, b: int) -> None:
    """
    Set LEDs from index `start` up to (but not including) `end`.
    Call write() to push to hardware.
    """
    for i in range(start, min(end, NUM_LEDS)):
        _np[i] = (_scale(r), _scale(g), _scale(b))


def clear() -> None:
    """Set all LEDs to off (0, 0, 0). Call write() to push to hardware."""
    _np.fill((0, 0, 0))


def write() -> None:
    """Push the pixel buffer to the LED strip. Blocks for ~55ms."""
    _np.write()


def set_all_and_show(r: int, g: int, b: int) -> None:
    """Convenience: fill all LEDs and immediately push to hardware."""
    set_all(r, g, b)
    write()


def set_one_and_show(index: int, r: int, g: int, b: int) -> None:
    """Convenience: set one LED and immediately push to hardware."""
    set_one(index, r, g, b)
    write()


def clear_and_show() -> None:
    """Convenience: clear all LEDs and immediately push to hardware."""
    clear()
    write()
