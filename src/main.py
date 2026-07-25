# main.py — ESP32-C3 firmware entry point
#
# Wires together buttons, LEDs, BLE scanner, and the pattern library.
# Runs at boot automatically when deployed to the device filesystem.

import utime
import machine
import buttons
import leds
import ble_scanner
import patterns


# ---------------------------------------------------------------------------
# Boot indication
# ---------------------------------------------------------------------------

leds.init()
utime.sleep_ms(500)
patterns.activate(0, 0)   # start on the first pattern + first palette


# ---------------------------------------------------------------------------
# Button callbacks
# Up    (S6, IO4) → next pattern
# Down  (S7, IO3) → BLE scan toggle (function will be rewritten later)
# Left  (S4, IO0) → previous palette
# Right (S5, IO2) → next palette
#
# NOTE: These run in ISR context — no blocking calls allowed (no leds.write()).
#       Set a flag and let the main loop do the actual LED update.
# ---------------------------------------------------------------------------

_pending         = None   # set by ISR, consumed by main loop
_current_pattern = 0
_current_palette = 0


def on_btn_up(pin_num):
    """Up (S6) — next pattern."""
    global _pending
    _pending = "next_pattern"


def on_btn_down(pin_num):
    """Down (S7) — BLE scan toggle."""
    global _pending
    _pending = "ble_toggle"


def on_btn_left(pin_num):
    """Left (S4) — previous palette."""
    global _pending
    _pending = "prev_palette"


def on_btn_right(pin_num):
    """Right (S5) — next palette."""
    global _pending
    _pending = "next_palette"


buttons.register_all(on_btn_up, on_btn_down, on_btn_left, on_btn_right)
print("[main] Buttons registered: Up=IO4 Down=IO3 Left=IO0 Right=IO2")


# ---------------------------------------------------------------------------
# BLE active scan — started on demand by Down (S7, IO3), not at boot
# ---------------------------------------------------------------------------

_ble_initialized = False
_ble_scanning    = False


# ---------------------------------------------------------------------------
# Main loop — keep firmware alive; all work is interrupt/callback driven
# ---------------------------------------------------------------------------

print("[main] System ready. Pattern 0: {} / palette 0: {}".format(
    patterns.pattern_name(0), patterns.palette_name(0)))

while True:
    if _pending is not None:
        action   = _pending
        _pending = None

        if action == "next_pattern":
            _current_pattern = (_current_pattern + 1) % patterns.pattern_count()
            print("[btn] Up — pattern {}: {}".format(_current_pattern, patterns.pattern_name(_current_pattern)))
            patterns.activate(_current_pattern, _current_palette)

        elif action == "prev_palette":
            _current_palette = (_current_palette - 1) % patterns.palette_count()
            print("[btn] Left — palette {}: {}".format(_current_palette, patterns.palette_name(_current_palette)))
            patterns.activate(_current_pattern, _current_palette)

        elif action == "next_palette":
            _current_palette = (_current_palette + 1) % patterns.palette_count()
            print("[btn] Right — palette {}: {}".format(_current_palette, patterns.palette_name(_current_palette)))
            patterns.activate(_current_pattern, _current_palette)

        elif action == "ble_toggle":
            if not _ble_scanning:
                if not _ble_initialized:
                    ble_scanner.init()
                    _ble_initialized = True
                print("[btn] Down — starting BLE scan")
                ble_scanner.start_scan(interval_us=100_000, window_us=10_000)
                _ble_scanning = True
                leds.set_all(0, 0, 7)   # dim blue = scanning
                leds.write()
            else:
                print("[btn] Down — stopping BLE scan, results:")
                ble_scanner.stop_scan()
                _ble_scanning = False
                results = ble_scanner.get_results()
                if not results:
                    print("  (no SCAN_RSP packets captured)")
                for rec in results:
                    addr_str = ble_scanner.format_addr(rec["addr"])
                    ad       = ble_scanner.parse_ad_structures(rec["data"])
                    dev_name = ad.get(0x09, ad.get(0x08, b"")).decode("utf-8", "ignore")
                    print("  {}  rssi={:4d}  name='{}'  raw={}".format(
                        addr_str, rec["rssi"], dev_name, rec["data"].hex()))
                # resume the current pattern/palette where scanning left off
                patterns.activate(_current_pattern, _current_palette)

    # Pause animation while scanning so the solid-blue indicator isn't overwritten.
    if not _ble_scanning:
        patterns.tick(_current_pattern, _current_palette, utime.ticks_ms())
    # Animation tick granularity: no pattern can advance faster than this, so it
    # sets the floor on every *_STEP_MS in patterns.py. 50ms matches the fastest
    # pattern (psychedelic) and keeps wakeups low for battery/lightsleep use.
    #machine.lightsleep(100)
    utime.sleep_ms(50)
