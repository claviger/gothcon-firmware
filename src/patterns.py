# patterns.py — LED pattern library (colour-agnostic)
#
# Two independent axes:
#   * pattern — *how* the body animates (solid, chase, twinkle, wash, swap, breathe)
#   * palette — *which* colours it uses, passed in as an argument
#
# A pattern never bakes in its own colours; activate()/tick() receive the palette
# so the running pattern re-renders whenever the palette is changed at runtime.
#
# Each pattern is a dict:
#   "name"  : str
#   "start" : callable(colors)        — render the initial frame
#   "tick"  : callable(colors, t_ms)  — advance the animation, or None if static
# where `colors` is a list of (r, g, b) tuples on the 0–10 brightness scale.
#
# The body (everything except the eyes) is addressed through leds.set_body_*();
# the bat eyes (leds.EYES) are driven separately by each pattern — by default a
# shade of white, with per-pattern dynamics (steady, pulse, counter-pulse).

import utime
import random

import leds

# --- animation timing / shape constants (exposed so tests are deterministic) ---
#
# A pattern can only advance as often as main.py calls tick(), so the main loop
# period is the floor on every step below. That loop is 20ms, which means these
# values are now the real on-badge cadence (they used to be rounded up to the
# old 100ms loop — e.g. chase actually ran at 200ms, breathe at 100ms/step).
# They are set to those previously-effective values so existing patterns look
# exactly as they did before the loop was shortened for `psychadelic`.
CHASE_STEP_MS   = 200
WASH_STEP_MS    = 200
SWAP_STEP_MS    = 400
SWAP_BLOCK      = 2      # body LEDs per colour block in the swap pattern
BREATHE_STEP_MS = 100
BREATHE_LEVELS  = 10     # brightness steps from off to full in one breath
TWINKLE_STEP_MS = 100
TWINKLE_DECAY   = 2      # per-step fade applied to each lit channel (0–10 scale)
TWINKLE_SPAWN   = 2      # max new twinkles spawned per step
PSYCH_STEP_MS   = 50     # psychadelic: dwell per colour (fast strobe)

EYE_WHITE = (10, 10, 10)


# ---------------------------------------------------------------------------
# Palettes — add new ones here; each is a list of (r, g, b) on the 0–10 scale.
# ---------------------------------------------------------------------------

PALETTES = [
    {"name": "rainbow",  "colors": [(10, 0, 0), (10, 3, 0), (10, 10, 0),
                                    (0, 10, 0), (0, 0, 10), (0, 0, 7), (7, 0, 10)]},
    {"name": "rip",      "colors": [(10, 0, 0), (0, 0, 7), (7, 0, 10)]},
    {"name": "ember",    "colors": [(10, 0, 0), (10, 3, 0), (10, 7, 0)]},
    {"name": "ghost",    "colors": [(10, 10, 10), (0, 8, 10), (2, 4, 10)]},
    {"name": "blood",    "colors": [(10, 0, 0), (6, 0, 0), (10, 2, 2)]},
    {"name": "amethyst", "colors": [(7, 0, 10), (4, 0, 8), (9, 2, 10)]},
]


def _pulse(t_ms, period, lo, hi):
    """Triangle wave in [lo, hi] over `period` ms (lo at phase 0, hi at half)."""
    phase = (t_ms % period) / period          # 0..1
    tri = 1.0 - abs(2.0 * phase - 1.0)         # 0..1..0
    return int(round(lo + (hi - lo) * tri))


# ---------------------------------------------------------------------------
# Pattern factories — each owns a private state dict.
# ---------------------------------------------------------------------------

def _make_solid():
    """All body LEDs hold the first palette colour; static. Eyes steady white."""
    def start(colors):
        c = colors[0]
        leds.set_body_all(c[0], c[1], c[2])
        leds.set_eyes(*EYE_WHITE)
        leds.write()
    return {"name": "solid", "start": start, "tick": None}


def _make_chase():
    """Palette colours chase along the body. Eyes steady white."""
    st = {"offset": 0, "last_ms": None}

    def _render(colors, offset):
        n = len(colors)
        for pos in range(leds.BODY_COUNT):
            c = colors[(pos + offset) % n]
            leds.set_body_logical(pos, c[0], c[1], c[2])
        leds.set_eyes(*EYE_WHITE)
        leds.write()

    def start(colors):
        st["offset"] = 0
        st["last_ms"] = None
        _render(colors, 0)

    def tick(colors, t_ms):
        if st["last_ms"] is None:
            st["last_ms"] = t_ms
            return
        if utime.ticks_diff(t_ms, st["last_ms"]) >= CHASE_STEP_MS:
            st["last_ms"] = t_ms
            st["offset"] = (st["offset"] + 1) % len(colors)
            _render(colors, st["offset"])

    return {"name": "chase", "start": start, "tick": tick}


def _make_twinkle():
    """Body mostly off; random LEDs flash in random palette colours and fade.

    Eyes slow-pulse white.
    """
    st = {"pix": None, "last_ms": None}

    def _fresh():
        return [[0, 0, 0] for _ in range(leds.BODY_COUNT)]

    def _render(t_ms):
        for pos in range(leds.BODY_COUNT):
            p = st["pix"][pos]
            leds.set_body_logical(pos, p[0], p[1], p[2])
        lvl = _pulse(t_ms, 2000, 2, 10)        # slow white pulse
        leds.set_eyes(lvl, lvl, lvl)
        leds.write()

    def start(colors):
        st["pix"] = _fresh()
        st["last_ms"] = None
        _render(0)

    def tick(colors, t_ms):
        if st["pix"] is None:
            st["pix"] = _fresh()
        if st["last_ms"] is None:
            st["last_ms"] = t_ms
            return
        if utime.ticks_diff(t_ms, st["last_ms"]) >= TWINKLE_STEP_MS:
            st["last_ms"] = t_ms
            for p in st["pix"]:                # fade everything toward off
                for k in range(3):
                    if p[k] > 0:
                        p[k] = max(0, p[k] - TWINKLE_DECAY)
            for _ in range(TWINKLE_SPAWN):     # spawn a few new sparkles
                if random.random() < 0.5:
                    pos = random.randrange(leds.BODY_COUNT)
                    c = colors[random.randrange(len(colors))]
                    st["pix"][pos] = [c[0], c[1], c[2]]
        _render(t_ms)

    return {"name": "twinkle", "start": start, "tick": tick}


def _make_wash():
    """One colour floods across the body; at the end the next colour washes over.

    Eyes steady white (contrast).
    """
    st = {"color_idx": 0, "head": 0, "last_ms": None}

    def start(colors):
        st["color_idx"] = 0
        st["head"] = 0
        st["last_ms"] = None
        leds.clear_body()
        leds.set_eyes(*EYE_WHITE)
        leds.write()

    def tick(colors, t_ms):
        if st["last_ms"] is None:
            st["last_ms"] = t_ms
            return
        if utime.ticks_diff(t_ms, st["last_ms"]) >= WASH_STEP_MS:
            st["last_ms"] = t_ms
            c = colors[st["color_idx"]]
            leds.set_body_logical(st["head"], c[0], c[1], c[2])
            leds.write()
            st["head"] += 1
            if st["head"] >= leds.BODY_COUNT:
                st["head"] = 0
                st["color_idx"] = (st["color_idx"] + 1) % len(colors)

    return {"name": "wash", "start": start, "tick": tick}


def _make_swap():
    """Body split into colour blocks that rotate which colour they show.

    Eyes steady white.
    """
    st = {"rot": 0, "last_ms": None}

    def _render(colors, rot):
        n = len(colors)
        for pos in range(leds.BODY_COUNT):
            c = colors[((pos // SWAP_BLOCK) + rot) % n]
            leds.set_body_logical(pos, c[0], c[1], c[2])
        leds.set_eyes(*EYE_WHITE)
        leds.write()

    def start(colors):
        st["rot"] = 0
        st["last_ms"] = None
        _render(colors, 0)

    def tick(colors, t_ms):
        if st["last_ms"] is None:
            st["last_ms"] = t_ms
            return
        if utime.ticks_diff(t_ms, st["last_ms"]) >= SWAP_STEP_MS:
            st["last_ms"] = t_ms
            st["rot"] = (st["rot"] + 1) % len(colors)
            _render(colors, st["rot"])

    return {"name": "swap", "start": start, "tick": tick}


def _make_breathe():
    """Whole body fades one colour up and down; eyes counter-pulse white.

    Each completed breath advances to the next palette colour.
    """
    st = {"color_idx": 0, "step": 0, "dir": 1, "last_ms": None}

    def _render(colors):
        c = colors[st["color_idx"]]
        f = st["step"]
        leds.set_body_all((c[0] * f) // BREATHE_LEVELS,
                          (c[1] * f) // BREATHE_LEVELS,
                          (c[2] * f) // BREATHE_LEVELS)
        e = (10 * (BREATHE_LEVELS - f)) // BREATHE_LEVELS   # bright when body dim
        leds.set_eyes(e, e, e)
        leds.write()

    def start(colors):
        st["color_idx"] = 0
        st["step"] = 0
        st["dir"] = 1
        st["last_ms"] = None
        _render(colors)

    def tick(colors, t_ms):
        if st["last_ms"] is None:
            st["last_ms"] = t_ms
            return
        if utime.ticks_diff(t_ms, st["last_ms"]) >= BREATHE_STEP_MS:
            st["last_ms"] = t_ms
            st["step"] += st["dir"]
            if st["step"] >= BREATHE_LEVELS:
                st["step"] = BREATHE_LEVELS
                st["dir"] = -1
            elif st["step"] <= 0:
                st["step"] = 0
                st["dir"] = 1
                st["color_idx"] = (st["color_idx"] + 1) % len(colors)
            _render(colors)

    return {"name": "breathe", "start": start, "tick": tick}


def _make_psychadelic():
    """Whole body strobes through the palette colours together, very fast.

    Every body LED shows the same colour at once (all red, then all orange, ...)
    advancing every PSYCH_STEP_MS. The eyes are deliberately excluded from the
    cycle and held steady white.
    """
    st = {"idx": 0, "last_ms": None}

    def _render(colors, idx):
        c = colors[idx]
        leds.set_body_all(c[0], c[1], c[2])
        leds.set_eyes(*EYE_WHITE)
        leds.write()

    def start(colors):
        st["idx"] = 0
        st["last_ms"] = None
        _render(colors, 0)

    def tick(colors, t_ms):
        if st["last_ms"] is None:
            st["last_ms"] = t_ms
            return
        if utime.ticks_diff(t_ms, st["last_ms"]) >= PSYCH_STEP_MS:
            st["last_ms"] = t_ms
            st["idx"] = (st["idx"] + 1) % len(colors)
            _render(colors, st["idx"])

    return {"name": "psychadelic", "start": start, "tick": tick}


# ---------------------------------------------------------------------------
# Pattern registry — order defines the index seen by main.py / the buttons.
# ---------------------------------------------------------------------------

_PATTERNS = [
    _make_solid(),
    _make_chase(),
    _make_twinkle(),
    _make_wash(),
    _make_swap(),
    _make_breathe(),
    _make_psychadelic(),
]


# ---------------------------------------------------------------------------
# Public API — two axes (pattern index, palette index)
# ---------------------------------------------------------------------------

def pattern_count():
    """Number of patterns in the library."""
    return len(_PATTERNS)


def pattern_name(i):
    """Name of the pattern at index *i*."""
    return _PATTERNS[i]["name"]


def palette_count():
    """Number of palettes available."""
    return len(PALETTES)


def palette_name(j):
    """Name of the palette at index *j*."""
    return PALETTES[j]["name"]


def _colors(j):
    return PALETTES[j]["colors"]


def activate(pattern_i, palette_j):
    """Start pattern *pattern_i* rendered with palette *palette_j* (resets state)."""
    _PATTERNS[pattern_i]["start"](_colors(palette_j))


def tick(pattern_i, palette_j, t_ms):
    """Advance the active pattern; no-op for static patterns."""
    fn = _PATTERNS[pattern_i]["tick"]
    if fn is not None:
        fn(_colors(palette_j), t_ms)
