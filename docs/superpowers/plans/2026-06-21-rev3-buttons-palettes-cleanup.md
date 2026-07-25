# rev3: Button Names/Mappings, Tick Rate, Spelling, Palettes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five rev3 changes: fix "psychedelic" spelling, restore a 50 ms main-loop tick, name the badge buttons (Up/Down/Left/Right with S-numbers) in code and docs, remap buttons (Up=next pattern, Left=prev palette, Right=next palette, Down=BLE), and add four new palettes.

**Architecture:** No structural changes — the two-axis pattern/palette design stays. `buttons.py` gains named pin constants and a name-based `register_all`; the test harness gains fake `machine`/`micropython` modules so `buttons.py` becomes host-testable for the first time. `main.py` swaps its action set (drops `prev_pattern`, adds `prev_palette`).

**Tech Stack:** MicroPython (device), CPython 3 + stdlib `unittest` (host tests via `tests/harness.py` fakes).

**Branch:** `rev3` (already created from `rev2`).

**Confirmed button map** (from user, resolving the spec's IO conflict):

| Name | Silkscreen | GPIO |
|------|-----------|------|
| Up | S6 | IO4 |
| Down | S7 | IO3 |
| Left | S4 | IO0 |
| Right | S5 | IO2 |

S3 = BOOT and S2 = RESET are separate hardware buttons, on none of these GPIOs. Stop calling IO0 "BOOT".

**Change-2 decision (tick rate):** Implement the revert to 50 ms. With today's `utime.sleep_ms()` loop the power delta is small (CPU stays clocked), but the project's stated direction is `machine.lightsleep()` on the battery-capable board, where wakeups/sec directly cost battery — and psychedelic still delivers 20 colour-changes/sec at a 50 ms tick, so there is no visual cost. **Keep** the rebased step constants (CHASE 200, WASH 200, TWINKLE 100, BREATHE 100, SWAP 400): they are the true historical on-badge cadences and all are multiples of 50, so the badge looks identical. Reverting them to the pre-rev2 literals (150/120/40/90) would *speed up* chase under a 50 ms tick (150 is now reachable) — the opposite of "undo".

**Verification command (all tasks):** `python -B -m unittest discover -s tests`
**Compile check:** `python -m py_compile src/leds.py src/patterns.py src/main.py src/buttons.py src/ble_scanner.py`

---

### Task 1: Fix "psychedelic" spelling everywhere

**Files:**
- Modify: `tests/test_patterns.py:12` (constant), `:41` (name assertion), `:153-168` (test class)
- Modify: `src/patterns.py:32` (comment), `:42` (constant comment), `:264-293` (factory), `:307` (registry)
- Modify: `src/main.py:133` (comment)
- Modify: `README.md:46` (patterns table row)

- [ ] **Step 1: Update the tests to expect the correct spelling**

In `tests/test_patterns.py` line 12:
```python
SOLID, CHASE, TWINKLE, WASH, SWAP, BREATHE, PSYCHEDELIC = range(7)
```
Line 41:
```python
        self.assertEqual(patterns.pattern_name(PSYCHEDELIC), "psychedelic")
```
Rename the class at line 153 and every `PSYCHADELIC` inside it:
```python
class TestPsychedelic(_Base):
    def test_whole_body_shows_a_single_palette_color(self):
        patterns.activate(PSYCHEDELIC, 0)
        first = scaled(patterns.PALETTES[0]["colors"][0])
        for pos in range(leds.BODY_COUNT):
            self.assertEqual(self.body(pos), first)   # every body LED identical
        self.assert_eyes_white()

    def test_advances_to_next_palette_color_after_step(self):
        patterns.activate(PSYCHEDELIC, 0)
        colors = patterns.PALETTES[0]["colors"]
        patterns.tick(PSYCHEDELIC, 0, 0)                      # init last_ms
        patterns.tick(PSYCHEDELIC, 0, patterns.PSYCH_STEP_MS)
        nxt = scaled(colors[1])
        for pos in range(leds.BODY_COUNT):
            self.assertEqual(self.body(pos), nxt)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -B -m unittest discover -s tests`
Expected: FAIL — `AssertionError: 'psychadelic' != 'psychedelic'`

- [ ] **Step 3: Fix the source**

In `src/patterns.py`: rename `_make_psychadelic` → `_make_psychedelic` (def at line 264 and the registry entry at line 307), change the returned `"name"` to `"psychedelic"`, and fix the words `psychadelic` in the comments at lines 32 and 42. In `src/main.py` line 133, change `` `psychadelic` `` to `` `psychedelic` ``. In `README.md` line 46, change `` `psychadelic` `` to `` `psychedelic` ``.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -B -m unittest discover -s tests`
Expected: `Ran 36 tests ... OK`. Also run: `git grep -i psychadelic` → no matches in tracked files.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Fix spelling: psychadelic -> psychedelic"
```

---

### Task 2: Restore 50 ms main-loop tick

**Files:**
- Modify: `src/main.py:130-135` (loop tail)
- Modify: `src/patterns.py:25-33` (constants comment block)

No unit test: `main.py` is not host-importable (it runs the device loop at import), and no pattern constant changes value. Verification is compile + full suite.

- [ ] **Step 1: Change the loop period**

Replace the loop tail in `src/main.py` (currently the comment + `utime.sleep_ms(20)`):
```python
    # Animation tick granularity: no pattern can advance faster than this, so it
    # sets the floor on every *_STEP_MS in patterns.py. 50ms matches the fastest
    # pattern (psychedelic) and keeps wakeups low for battery/lightsleep use.
    #machine.lightsleep(100)
    utime.sleep_ms(50)
```

- [ ] **Step 2: Update the patterns.py constants comment**

Replace the comment block above the constants (lines 25–33, the paragraph explaining the 20 ms loop) with:
```python
# --- animation timing / shape constants (exposed so tests are deterministic) ---
#
# A pattern can only advance as often as main.py calls tick(), so the main-loop
# period (50ms) is the floor on every step below. All values are multiples of
# 50ms so the rendered cadence is exact, and they match the on-badge speeds the
# patterns have had since rev2.
```

- [ ] **Step 3: Verify**

Run: `python -m py_compile src/patterns.py src/main.py` → exit 0.
Run: `python -B -m unittest discover -s tests` → `OK`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Restore 50ms main-loop tick for battery/lightsleep headroom"
```

---

### Task 3: Named buttons in buttons.py (+ make it host-testable)

**Files:**
- Modify: `tests/harness.py` (add fake `machine` + `micropython`)
- Create: `tests/test_buttons.py`
- Modify: `src/buttons.py:1-11` (header), `:59-72` (`register_all`)
- Modify: `README.md:14-20` (hardware table), `:170-184` (buttons module reference)

- [ ] **Step 1: Add fake machine/micropython to the harness**

Append to `tests/harness.py` (after the `FakeStrip` class):
```python
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
        FakePin.instances[pin_num] = self

    def irq(self, trigger=None, handler=None):
        self.trigger = trigger
        self.handler = handler

    def press(self):
        """Test helper: simulate the falling-edge interrupt firing."""
        if self.handler:
            self.handler(self)


_fake_machine = types.ModuleType("machine")
_fake_machine.Pin = FakePin
sys.modules["machine"] = _fake_machine

# micropython.schedule() defers a soft callback; on the host, run it immediately.
_fake_micropython = types.ModuleType("micropython")
_fake_micropython.schedule = lambda fn, arg: fn(arg)
sys.modules["micropython"] = _fake_micropython
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_buttons.py`:
```python
# test_buttons.py — named button map and IRQ/debounce dispatch.

import unittest

import harness  # noqa: F401  (sets sys.path, installs fake utime/machine/micropython)
from harness import FakePin, fake_utime
import buttons


class TestPinMap(unittest.TestCase):
    def test_named_pins_match_badge_silkscreen(self):
        self.assertEqual(buttons.PIN_UP, 4)     # S6
        self.assertEqual(buttons.PIN_DOWN, 3)   # S7
        self.assertEqual(buttons.PIN_LEFT, 0)   # S4
        self.assertEqual(buttons.PIN_RIGHT, 2)  # S5

    def test_named_pins_are_distinct(self):
        pins = {buttons.PIN_UP, buttons.PIN_DOWN, buttons.PIN_LEFT,
                buttons.PIN_RIGHT}
        self.assertEqual(len(pins), 4)


class TestRegisterAll(unittest.TestCase):
    def setUp(self):
        FakePin.instances.clear()
        self.presses = []
        buttons.register_all(
            lambda p: self.presses.append(("up", p)),
            lambda p: self.presses.append(("down", p)),
            lambda p: self.presses.append(("left", p)),
            lambda p: self.presses.append(("right", p)),
        )

    def test_configures_pullup_input_with_falling_irq(self):
        for pin_num in (buttons.PIN_UP, buttons.PIN_DOWN,
                        buttons.PIN_LEFT, buttons.PIN_RIGHT):
            pin = FakePin.instances[pin_num]
            self.assertEqual(pin.mode, FakePin.IN)
            self.assertEqual(pin.pull, FakePin.PULL_UP)
            self.assertEqual(pin.trigger, FakePin.IRQ_FALLING)
            self.assertIsNotNone(pin.handler)

    def test_press_dispatches_the_named_callback(self):
        fake_utime.advance(100)      # clear the registration debounce window
        FakePin.instances[buttons.PIN_UP].press()
        self.assertEqual(self.presses, [("up", buttons.PIN_UP)])

    def test_bounce_within_debounce_window_is_discarded(self):
        fake_utime.advance(100)
        FakePin.instances[buttons.PIN_LEFT].press()
        fake_utime.advance(buttons.DEBOUNCE_MS - 1)
        FakePin.instances[buttons.PIN_LEFT].press()   # bounce — ignored
        fake_utime.advance(buttons.DEBOUNCE_MS + 1)
        FakePin.instances[buttons.PIN_LEFT].press()   # genuine second press
        self.assertEqual([name for name, _ in self.presses], ["left", "left"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -B -m unittest discover -s tests`
Expected: FAIL — `AttributeError: module 'buttons' has no attribute 'PIN_UP'` (register_all also has the old `cb_io0...` signature).

- [ ] **Step 4: Update buttons.py**

Replace the header comment (lines 1–11) with:
```python
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
```
After `DEBOUNCE_MS = 50`, add:
```python
# Badge button map: name -> GPIO (silkscreen labels in comments)
PIN_UP    = 4   # S6
PIN_DOWN  = 3   # S7
PIN_LEFT  = 0   # S4
PIN_RIGHT = 2   # S5
```
Replace `register_all` (lines 59–72) with:
```python
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
```
Also update `register()`'s docstring arg line to `pin_num:  GPIO number (see PIN_UP/PIN_DOWN/PIN_LEFT/PIN_RIGHT)`.

**Note:** `main.py` still calls `register_all(on_btn_io0, ...)` positionally — the old first arg (IO0 callback) now lands on `cb_up`. That mis-wiring is fixed in Task 4; the full suite stays green in between because tests never import `main.py`. Do Task 4 before flashing a device.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -B -m unittest discover -s tests`
Expected: `OK` (5 new tests).

- [ ] **Step 6: Update README hardware table + buttons reference**

Replace the GPIO table rows (lines 14–20) with:
```markdown
| GPIO | Function |
|------|----------|
| IO4  | Up button (S6, active-low, internal pull-up) |
| IO3  | Down button (S7, active-low, internal pull-up) |
| IO0  | Left button (S4, active-low, internal pull-up) |
| IO2  | Right button (S5, active-low, internal pull-up) |
| IO10 | WS2812B data line (44 LEDs daisy-chained; eyes at indices 28 & 30) |

The badge's **BOOT (S3)** and **RESET (S2)** buttons are separate hardware
controls (used for flashing) and are not on these GPIOs.
```
Replace the `buttons` module-reference example with:
```python
import buttons

def my_callback(pin_num):
    print(f"GPIO {pin_num} pressed")

# Register all four directional buttons at once (Up, Down, Left, Right)
buttons.register_all(cb_up, cb_down, cb_left, cb_right)

# Or register individually using the named pins
buttons.register(buttons.PIN_LEFT, my_callback)
buttons.unregister(buttons.PIN_LEFT)
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Name the badge buttons (Up/Down/Left/Right, S4-S7) and test buttons.py"
```

---

### Task 4: Remap buttons in main.py (Up=next pattern, Left/Right=palette, Down=BLE)

**Files:**
- Modify: `src/main.py:24-62` (comment + callbacks + register_all), `:84-99` (actions), `:105,110` (BLE prints)
- Modify: `README.md:29-34` (controls table)

`main.py` is not host-importable, so verification is compile + suite + reading the diff.

- [ ] **Step 1: Replace the callbacks block**

Replace the comment + four `on_btn_io*` functions + `register_all` call (lines 24–62) with:
```python
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
```

- [ ] **Step 2: Replace the action handlers**

Replace the `prev_pattern`/`next_pattern`/`next_palette` handlers (the `if action ==` chain before `ble_toggle`) with:
```python
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
```
(`prev_pattern` is gone — no button maps to it.) In the BLE branch, change both `"[btn] IO4 pressed — starting BLE scan"` / `"[btn] IO4 pressed — stopping BLE scan, results:"` to `"[btn] Down — starting BLE scan"` / `"[btn] Down — stopping BLE scan, results:"`.

- [ ] **Step 3: Update the README controls table**

Replace the button table (lines 29–34) with:
```markdown
| Button | Action |
|--------|--------|
| Up (S6 / IO4) | Next pattern |
| Down (S7 / IO3) | Toggle BLE scan (solid blue while scanning; pattern resumes on stop) |
| Left (S4 / IO0) | Previous palette |
| Right (S5 / IO2) | Next palette |
```

- [ ] **Step 4: Verify**

Run: `python -m py_compile src/main.py` → exit 0.
Run: `python -B -m unittest discover -s tests` → `OK`.
Run: `git grep -n "prev_pattern\|on_btn_io\|BOOT button" src/` → no matches.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Remap buttons: Up=next pattern, Left/Right=palette, Down=BLE"
```

---

### Task 5: Add four new palettes

**Files:**
- Modify: `tests/test_patterns.py:44-46` (palette count test) + add a structure test in `TestApi`
- Modify: `src/patterns.py:47-54` (PALETTES)
- Modify: `README.md:50-51` (palettes line)

- [ ] **Step 1: Write the failing tests**

In `tests/test_patterns.py`, replace `test_palette_count_and_names` and add a structure test:
```python
    def test_palette_count_and_names(self):
        self.assertEqual(patterns.palette_count(), 10)
        self.assertEqual(patterns.palette_name(0), "rainbow")
        names = [patterns.palette_name(j) for j in range(patterns.palette_count())]
        for expected in ("halloween", "toxic", "ocean", "sunset"):
            self.assertIn(expected, names)

    def test_every_palette_is_well_formed(self):
        for pal in patterns.PALETTES:
            self.assertTrue(pal["colors"], pal["name"])
            for c in pal["colors"]:
                self.assertEqual(len(c), 3, pal["name"])
                for ch in c:
                    self.assertTrue(0 <= ch <= 10, pal["name"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -B -m unittest discover -s tests`
Expected: FAIL — `AssertionError: 6 != 10`

- [ ] **Step 3: Add the palettes**

Append to `PALETTES` in `src/patterns.py` (after `amethyst`):
```python
    {"name": "halloween", "colors": [(10, 3, 0), (6, 0, 10), (0, 10, 1), (10, 1, 0)]},
    {"name": "toxic",     "colors": [(2, 10, 0), (0, 10, 3), (6, 10, 0), (0, 6, 1)]},
    {"name": "ocean",     "colors": [(0, 2, 10), (0, 6, 10), (0, 10, 8), (2, 4, 8), (8, 10, 10)]},
    {"name": "sunset",    "colors": [(10, 1, 0), (10, 4, 0), (9, 0, 4), (5, 0, 7), (2, 0, 5)]},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -B -m unittest discover -s tests`
Expected: `OK`.

- [ ] **Step 5: Update the README palettes line**

```markdown
**Palettes** (0–10 brightness scale): `rainbow`, `rip`, `ember`, `ghost`,
`blood`, `amethyst`, `halloween`, `toxic`, `ocean`, `sunset`. Add more by
appending to `PALETTES` in `src/patterns.py`.
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Add halloween, toxic, ocean, and sunset palettes"
```

---

### Task 6: Final verification

- [ ] **Step 1: Full compile + suite**

Run: `python -m py_compile src/leds.py src/patterns.py src/main.py src/buttons.py src/ble_scanner.py` → exit 0.
Run: `python -B -m unittest discover -s tests -v` → all tests `ok`, summary `OK` (expect 42: 36 current + 5 new button tests + 1 net new palette test).

- [ ] **Step 2: Cross-checks**

- `git grep -i psychadelic` → no matches.
- `git grep -n "IO0 (BOOT\|BOOT button" README.md src/` → no matches presenting IO0 as BOOT (the flashing section's real BOOT/S3 instructions stay).
- `git log --oneline main..rev3` shows the five feature commits.

- [ ] **Step 3: Report** — summarize to the user; ask before pushing `rev3`.
