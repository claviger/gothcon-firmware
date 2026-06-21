# patterns.py — LED pattern library
#
# Each pattern is a dict with:
#   "name"  : str            — human-readable label
#   "start" : callable()     — called when the pattern is activated; renders initial state
#   "tick"  : callable(t_ms) — called every main-loop iteration with utime.ticks_ms(),
#             or None for static patterns
#
# To add a new pattern, append an entry to LIBRARY using _make_solid() for a static
# colour or a custom factory function for an animated pattern.

import leds
import utime

NUM_LEDS = 44

# Seven rainbow hues (0–10 brightness scale; actual power draw is limited by leds.BRIGHTNESS)
_RAINBOW_COLORS = [
    (10, 0,  0),  # red
    (10, 3,  0),  # orange
    (10, 10, 0),  # yellow
    (0,  10, 0),  # green
    (0,  0,  10), # blue
    (0,  0,  7),  # indigo
    (7,  0,  10), # violet
]


def _make_solid(name, r, g, b):
    """Factory: all LEDs solid colour, no animation."""
    def start():
        leds.set_all(r, g, b)
        leds.write()
    return {"name": name, "start": start, "tick": None}


def _make_chase(name, colors, step_ms=150):
    """Factory: a list of colours chase along the strip.

    Each LED takes the next colour in *colors*, and the whole pattern
    shifts by one LED every *step_ms* milliseconds.
    """
    n = len(colors)
    state = {"offset": 0, "last_ms": None}

    def _render(offset):
        for i in range(NUM_LEDS):
            c = colors[(i + offset) % n]
            leds.set_one(i, c[0], c[1], c[2])
        leds.write()

    def start():
        state["offset"] = 0
        state["last_ms"] = None   # will be initialised on the first tick
        _render(0)

    def tick(t_ms):
        if state["last_ms"] is None:
            state["last_ms"] = t_ms
            return
        if utime.ticks_diff(t_ms, state["last_ms"]) >= step_ms:
            state["last_ms"] = t_ms
            state["offset"] = (state["offset"] + 1) % n
            _render(state["offset"])

    return {"name": name, "start": start, "tick": tick}


# Three-colour palette: red, indigo, purple — each repeated for a 2-LED-wide chase
_RIP_COLORS = [
    (10, 0, 0),   # red
    (10, 0, 0),
    (0,  0, 7),   # indigo
    (0,  0, 7),
    (7,  0, 10),  # purple
    (7,  0, 10),
]


# ---------------------------------------------------------------------------
# Pattern library — add new patterns here
# ---------------------------------------------------------------------------

LIBRARY = [
    _make_solid("red",    10, 0,  0),
    _make_solid("orange", 10, 3,  0),
    _make_solid("yellow", 10, 10, 0),
    _make_solid("green",  0,  10, 0),
    _make_solid("blue",   0,  0,  10),
    _make_solid("indigo", 0,  0,  7),
    _make_solid("violet", 7,  0,  10),
    _make_chase("rainbow chase", _RAINBOW_COLORS, step_ms=150),
    _make_chase("RIP chase",     _RIP_COLORS,     step_ms=300),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def count():
    """Return the number of patterns in the library."""
    return len(LIBRARY)


def name(index):
    """Return the name of the pattern at *index*."""
    return LIBRARY[index]["name"]


def activate(index):
    """Activate (start) the pattern at *index*."""
    LIBRARY[index]["start"]()


def tick(index, t_ms):
    """Drive the current pattern forward; no-op for static patterns."""
    fn = LIBRARY[index]["tick"]
    if fn is not None:
        fn(t_ms)
