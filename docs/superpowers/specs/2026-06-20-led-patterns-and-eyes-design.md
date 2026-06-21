# LED Patterns & Bat Eyes — Design

**Date:** 2026-06-20
**Branch:** rev2
**Status:** Approved (pending spec review)

## Goal

Revise the LED subsystem so that:

1. **Patterns are color-agnostic.** A pattern no longer bakes in its own colors;
   it receives a *palette* as an argument. Pattern and palette become two
   independent axes that can be combined freely at runtime.
2. **Add new patterns** inspired by programmable Christmas lights: twinkle,
   wash (color wipe), swap/alternate, breathe — alongside the existing solid and
   chase.
3. **The bat eyes (LEDs 32 & 36) are a first-class concept.** A shared
   `leds.set_eyes()` helper drives them, and each pattern decides how its eyes
   behave (steady white, slow pulse, counter-pulse) — the eyes are never treated
   as part of the animated body.

## Non-goals (YAGNI / future)

- Per-palette eye accent colors. Eyes are **white** for now; the dynamics
  (steady / pulse / counter-pulse) differ per pattern, which already covers the
  "solid white or pulsating" requirement.
- Persisting the selected pattern/palette across reboots.
- BLE-reactive patterns.
- More patterns/palettes — the user may add these later; the interface is
  designed to make that a one-line addition to a list.

---

## Hardware layout (confirmed)

- `NUM_LEDS = 44` is **correct**. The README's "40" is wrong and will be fixed.
- **Eyes:** physical indices `32` and `36`.
- **Body:** the other 42 LEDs, in ascending physical-index order.

---

## Architecture

### `leds.py` — owns physical layout

Add layout constants and body/eye helpers; keep all existing functions.

```python
NUM_LEDS  = 44
EYES      = (32, 36)
BODY      = tuple(i for i in range(NUM_LEDS) if i not in EYES)  # 42 entries
BODY_COUNT = len(BODY)

def set_eyes(r, g, b): ...          # set both eye LEDs (scaled); no write
def set_body_all(r, g, b): ...      # fill only BODY (eyes untouched); no write
def set_body_logical(pos, r, g, b): # address the Nth body LED (0..41) -> BODY[pos]
def clear_body(): ...               # set_body_all(0, 0, 0)
```

Patterns address the body through `set_body_*` (logical positions `0..41`), so a
chase/wash looks contiguous and can never accidentally color an eye.

**Host-testability requirement:** `leds.py` must be importable on a host PC
(CPython) without ESP hardware. Move `import neopixel` / `from machine import
Pin` out of module top-level and into `init()` (the only function that needs
them). Tests then import `leds`, set `leds._np = FakeStrip(NUM_LEDS)`, and
exercise the real `_scale` / `set_body_*` / `set_eyes` logic without calling
`init()`.

### `patterns.py` — patterns + palettes, two-axis API

A **palette** is data:

```python
PALETTES = [
    {"name": "rainbow",  "colors": [(10,0,0),(10,3,0),(10,10,0),(0,10,0),(0,0,10),(0,0,7),(7,0,10)]},
    {"name": "rip",      "colors": [(10,0,0),(0,0,7),(7,0,10)]},
    {"name": "ember",    "colors": [(10,0,0),(10,3,0),(10,7,0)]},
    {"name": "ghost",    "colors": [(10,10,10),(0,8,10),(2,4,10)]},
    {"name": "blood",    "colors": [(10,0,0),(6,0,0),(10,2,2)]},
    {"name": "amethyst", "colors": [(7,0,10),(4,0,8),(9,2,10)]},
]
```
(Color tuples are on the 0–10 logical scale and are tunable during
implementation. The set is approved; more may be appended later.)

A **pattern** is a dict that owns its own state and takes a palette as an
argument (not at build time):

```python
{ "name": "twinkle",
  "start": fn(palette),          # render the initial frame for this palette
  "tick":  fn(palette, t_ms) }   # advance the animation (or None for static)
```

**Public API (two axes):**

```python
pattern_count();  pattern_name(i)
palette_count();  palette_name(j)
activate(pattern_i, palette_j)        # render initial frame
tick(pattern_i, palette_j, t_ms)      # advance; no-op for static patterns
```

**Palette/pattern change semantics:** Changing *either* axis calls
`activate(pattern_i, palette_j)` again, which resets the pattern's state and
re-renders with the current palette. This keeps the model trivial: the running
pattern always reflects the currently selected palette, and stateful patterns
(wash head position, twinkle states) simply restart on a change. Acceptable and
intended.

---

## Pattern catalog

All patterns animate the **body** only and set the **eyes** explicitly each
frame. Default eye color is white `(10,10,10)`; the *dynamics* differ per
pattern (table below).

| Pattern | Body behavior | Eyes |
|---------|---------------|------|
| **solid** | Fill body with `palette[0]`. Static (`tick = None`). | Steady white |
| **chase** | Body LED at logical `i` shows `colors[(i+offset) % n]`; `offset` advances one step every `step_ms` (~150 ms). | Steady white |
| **twinkle** | Body mostly off. Each tick: decay all lit body LEDs toward 0; with probability `p` spawn a few new lit LEDs at random body positions in random palette colors. Invariant: majority stay off (target ≥ ~70% off). | Slow pulse white |
| **wash** | A "head" advances across logical body positions every `step_ms`, painting the current color; when it reaches the end it switches to the next palette color and washes again from position 0 (new color floods over the old). Loops through the palette. | Steady white |
| **swap** | Body split into fixed-size blocks; each block colored by a palette color round-robin: `palette[((pos // block) + rot) % n]`. `rot` advances every `step_ms`, swapping which block shows which color (classic alternating string). | Steady white |
| **breathe** | Whole body holds one palette color, brightness fades up→down via an integer breath factor; at each full cycle advance to the next palette color. | Counter-pulse white (bright when body is dim) |

`Pattern order (indices):` solid, chase, twinkle, wash, swap, breathe.

### Eyes implementation notes

- Eye dynamics that animate (twinkle pulse, breathe counter-pulse) are computed
  from `t_ms` so they need no extra state beyond what the pattern already keeps.
- "Counter-pulse" = eye brightness is `max - body_breath_level`, so the eyes
  glow brightest at the body's dimmest point.

### Randomness (twinkle)

Twinkle uses the `random` module (available in both MicroPython and CPython).
Implementation must allow deterministic tests via `random.seed(...)`. Tests
either seed it or assert the statistical invariant (≥ ~70% of body off across
many frames).

---

## `main.py` — buttons & loop

| Button | Role |
|--------|------|
| IO0 | previous pattern |
| IO2 | next pattern |
| **IO3** | **next palette** (was unassigned) |
| IO4 | BLE scan toggle (unchanged) |

Changes:

- Track `_current_pattern` **and** `_current_palette`.
- New ISR action `"next_palette"` → `_current_palette = (_current_palette + 1) %
  patterns.palette_count()`, then `patterns.activate(_current_pattern,
  _current_palette)`.
- Pattern prev/next and palette-next all call `patterns.activate(pat, pal)`.
- Main loop calls `patterns.tick(_current_pattern, _current_palette,
  utime.ticks_ms())`.
- Boot: `patterns.activate(0, 0)`.

**BLE-indicator interaction (small fix):** today the loop ticks the pattern every
iteration, which would overwrite the solid-blue "scanning" indicator. While
`_ble_scanning` is true, **skip** `patterns.tick(...)`. On scan **stop**,
`patterns.activate(current_pattern, current_palette)` to resume the pattern
(instead of `clear_and_show()`).

---

## Cleanups

- Remove the duplicate `NUM_LEDS = 44` in `patterns.py`; reference
  `leds.NUM_LEDS` / `leds.BODY` instead (single source of truth).
- Update `README.md`:
  - Fix LED count 40 → 44.
  - Document the eyes (indices 32 & 36) and the `set_eyes` helper.
  - Document the new patterns, the palette list, and the IO3 = palette role.

---

## Testing (host-side, CPython, no device)

`patterns.py` depends only on `leds` and `utime`, and `leds.py` will be
host-importable, so the rendering logic can be fully tested on a PC.

**Test scaffolding (`tests/`):**

- `FakeStrip(n)` — a list-like buffer supporting `__setitem__`, `__getitem__`,
  `fill`, `__len__`, `write()`. Assigned to `leds._np` in test setup so the
  **real** `leds` helpers run against it.
- `fake_utime` — injected via `sys.modules` before importing `patterns`;
  provides a controllable `ticks_ms()` plus `ticks_diff()` / `sleep_ms()`.
- Plain `unittest` (stdlib) so no new dependency is added; run with
  `python -m unittest discover tests`.

**Representative tests:**

1. `BODY` excludes 32 & 36, `len(BODY) == 42`, eyes ∉ BODY.
2. `set_eyes()` writes the scaled color to indices 32 & 36 only.
3. **solid:** every body LED equals `palette[0]`; eyes are white; no eye index
   holds a body color.
4. **chase:** after several ticks, indices 32 & 36 are always eye-white and
   never take a chase body color.
5. **wash:** the head advances; after `BODY_COUNT` steps the whole body is
   `color[0]`, then the color switches to `color[1]`; eyes stay white throughout.
6. **twinkle:** across N ticks (seeded), the fraction of lit body LEDs stays
   below the threshold (majority off).
7. **swap:** block colors rotate across intervals.
8. **breathe:** at the body's dimmest frame the eye brightness is near maximum
   (counter-pulse).
9. **palette change:** `activate(p, A)` then `activate(p, B)` re-colors the body
   with palette B's colors.

---

## File change summary

| File | Change |
|------|--------|
| `src/leds.py` | Add `EYES`, `BODY`, `BODY_COUNT`; defer hardware imports into `init()`; add `set_eyes`, `set_body_all`, `set_body_logical`, `clear_body`. |
| `src/patterns.py` | New palette-as-argument pattern interface; `PALETTES`; six patterns; two-axis public API; drop duplicate `NUM_LEDS`. |
| `src/main.py` | Track palette index; IO3 → next palette; pass palette to activate/tick; skip tick while scanning; reactivate pattern on scan stop. |
| `README.md` | Fix LED count; document eyes, patterns, palettes, IO3 role. |
| `tests/` (new) | `FakeStrip`, `fake_utime`, and `unittest` tests listed above. |
