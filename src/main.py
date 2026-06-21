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
# IO0 = BOOT button  → previous pattern
# IO2               → next pattern
# IO3               → next palette (colour set the current pattern renders with)
# IO4               → BLE toggle (unchanged)
#
# NOTE: These run in ISR context — no blocking calls allowed (no leds.write()).
#       Set a flag and let the main loop do the actual LED update.
# ---------------------------------------------------------------------------

_pending         = None   # set by ISR, consumed by main loop
_current_pattern = 0
_current_palette = 0


def on_btn_io0(pin_num):
    """IO0 pressed — previous pattern."""
    global _pending
    _pending = "prev_pattern"


def on_btn_io2(pin_num):
    """IO2 pressed — next pattern."""
    global _pending
    _pending = "next_pattern"


def on_btn_io3(pin_num):
    """IO3 pressed — next palette."""
    global _pending
    _pending = "next_palette"


def on_btn_io4(pin_num):
    """IO4 pressed — start scan, or stop and dump results if already scanning."""
    global _pending
    _pending = "ble_toggle"


buttons.register_all(on_btn_io0, on_btn_io2, on_btn_io3, on_btn_io4)
print("[main] Buttons registered on IO0, IO2, IO3, IO4")


# ---------------------------------------------------------------------------
# BLE active scan — started on demand by IO4, not at boot
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

        if action == "prev_pattern":
            _current_pattern = (_current_pattern - 1) % patterns.pattern_count()
            print("[btn] IO0 — pattern {}: {}".format(_current_pattern, patterns.pattern_name(_current_pattern)))
            patterns.activate(_current_pattern, _current_palette)

        elif action == "next_pattern":
            _current_pattern = (_current_pattern + 1) % patterns.pattern_count()
            print("[btn] IO2 — pattern {}: {}".format(_current_pattern, patterns.pattern_name(_current_pattern)))
            patterns.activate(_current_pattern, _current_palette)

        elif action == "next_palette":
            _current_palette = (_current_palette + 1) % patterns.palette_count()
            print("[btn] IO3 — palette {}: {}".format(_current_palette, patterns.palette_name(_current_palette)))
            patterns.activate(_current_pattern, _current_palette)

        elif action == "ble_toggle":
            if not _ble_scanning:
                if not _ble_initialized:
                    ble_scanner.init()
                    _ble_initialized = True
                print("[btn] IO4 pressed — starting BLE scan")
                ble_scanner.start_scan(interval_us=100_000, window_us=10_000)
                _ble_scanning = True
                leds.set_all(0, 0, 7)   # dim blue = scanning
                leds.write()
            else:
                print("[btn] IO4 pressed — stopping BLE scan, results:")
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
    #machine.lightsleep(100)
    utime.sleep_ms(100)
