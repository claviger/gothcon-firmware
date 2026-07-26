# main.py — ESP32-C3 firmware entry point
#
# Wires together buttons, LEDs, the pattern library, and the wireless
# contagion effect. Runs at boot automatically when deployed to the device.

import utime
import buttons
import leds
import patterns
import contagion


# ---------------------------------------------------------------------------
# Boot indication
# ---------------------------------------------------------------------------

leds.init()
utime.sleep_ms(500)
patterns.activate(0, 0)   # start on the first pattern + first palette
contagion.init(patterns.pattern_count(), patterns.palette_count())


# ---------------------------------------------------------------------------
# Button callbacks
# Up    (S6, IO4) → next pattern
# Down  (S7, IO3) → tap: broadcast pattern to nearby badges ("infect")
#                   hold 5s: wireless opt-out (until power cycle)
# Left  (S4, IO0) → previous palette
# Right (S5, IO2) → next palette
#
# NOTE: These run in ISR context — no blocking calls allowed (no leds.write()).
#       Set a flag and let the main loop do the actual LED update.
# ---------------------------------------------------------------------------

_pending         = None   # set by ISR, consumed by main loop
_current_pattern = 0
_current_palette = 0
_down_held_since = None   # ticks_ms when Down went low; None = not watching


def on_btn_up(pin_num):
    """Up (S6) — next pattern."""
    global _pending
    _pending = "next_pattern"


def on_btn_down(pin_num):
    """Down (S7) — start the tap-vs-hold watcher."""
    global _pending
    _pending = "down_press"


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
# Main loop — keep firmware alive; all work is interrupt/callback driven
# ---------------------------------------------------------------------------

print("[main] System ready. Pattern 0: {} / palette 0: {}".format(
    patterns.pattern_name(0), patterns.palette_name(0)))

while True:
    now = utime.ticks_ms()

    if _pending is not None:
        action   = _pending
        _pending = None
        # Any button interaction mutes incoming infections for a grace period
        # so nobody's selection gets overwritten mid-browse.
        contagion.notify_user_activity(now)

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

        elif action == "down_press":
            if _down_held_since is None:
                _down_held_since = now

    # Down tap-vs-hold watcher: release before the hold threshold broadcasts
    # our look; holding to the threshold opts out of wireless until reboot.
    if _down_held_since is not None:
        held_ms = utime.ticks_diff(now, _down_held_since)
        if not buttons.is_pressed(buttons.PIN_DOWN):
            _down_held_since = None
            if held_ms < contagion.OPTOUT_HOLD_MS:
                if contagion.broadcast(_current_pattern, _current_palette, now):
                    print("[btn] Down — broadcasting pattern {} / palette {}".format(
                        patterns.pattern_name(_current_pattern),
                        patterns.palette_name(_current_palette)))
        elif held_ms >= contagion.OPTOUT_HOLD_MS:
            _down_held_since = None
            print("[btn] Down held {}ms — wireless opt-out until power cycle".format(held_ms))
            leds.set_all_and_show(10, 10, 10)         # confirm: all white...
            utime.sleep_ms(contagion.OPTOUT_FLASH_MS)  # ...for half a second
            contagion.opt_out()
            patterns.activate(_current_pattern, _current_palette)

    # Wireless: run the listen/burst scheduler and adopt any incoming look.
    infected = contagion.service(now)
    if infected is not None:
        _current_pattern, _current_palette = infected
        print("[rf] infected — pattern {}: {} / palette {}: {}".format(
            _current_pattern, patterns.pattern_name(_current_pattern),
            _current_palette, patterns.palette_name(_current_palette)))
        patterns.activate(_current_pattern, _current_palette)

    patterns.tick(_current_pattern, _current_palette, now)
    # Animation tick granularity: no pattern can advance faster than this, so it
    # sets the floor on every *_STEP_MS in patterns.py. 50ms matches the fastest
    # pattern (psychedelic) and keeps wakeups low for battery/lightsleep use.
    #machine.lightsleep(100)   # (re-add `import machine` when enabling this)
    utime.sleep_ms(50)
