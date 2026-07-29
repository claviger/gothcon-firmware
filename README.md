# Gothcon 2026 Badge

MicroPython firmware for an ESP32-C3 convention badge with:
- Four interrupt-driven directional pushbuttons (Up/Down/Left/Right, S4–S7)
- 44 WS2812B (NeoPixel) addressable RGB LEDs on IO10 — including two "bat eye"
  LEDs (indices **28** and **30**) driven independently of the animated body
- A library of colour-agnostic **patterns** combined with selectable **palettes**
- A wireless **contagion** effect (ESP-NOW): tap Down and nearby badges adopt
  your pattern + palette, cascading a few hops through the room

---

## Hardware

| GPIO | Function |
|------|----------|
| IO4  | Up button (S6, active-low, internal pull-up) |
| IO3  | Down button (S7, active-low, internal pull-up) |
| IO0  | Left button (S4, active-low, internal pull-up) |
| IO2  | Right button (S5, active-low, internal pull-up) |
| IO10 | WS2812B data line (44 LEDs daisy-chained; eyes at indices 28 & 30) |

The badge's **BOOT (S3)** and **RESET (S2)** buttons are separate hardware
controls (used for flashing) and are not on these GPIOs.

---

## Operating the badge

Power the badge on and it starts animating immediately. It shows one
**pattern** rendered with one **palette** — two independent axes, so any
pattern can be combined with any palette at runtime.

| Button | Location / GPIO | Action |
|--------|-----------------|--------|
| Up (S6) | IO4 | Next pattern |
| Down (S7) | IO3 | Tap: infect nearby badges with your pattern. Hold 5 s: disable wireless (see below) |
| Left (S4) | IO0 | Previous palette |
| Right (S5) | IO2 | Next palette |
| RESET (S2) | left of the microcontroller | Reboot the badge — restarts the app and re-enables contagion after an opt-out |
| BOOT (S3) | below the microcontroller, left side | Flashing only: hold while pressing RESET to force download mode (usually unnecessary — `flash.py` does this itself) |

### How the contagion works

Tapping **Down** broadcasts your current pattern + palette over ESP-NOW;
badges that hear it switch to match and re-broadcast, cascading up to ~3 hops
(~1 s per hop, so it ripples through the room rather than instantly taking it
over). Safeguards: each press has a unique id so it never loops through a
badge twice; a badge accepts at most one press per origin every 6 s and can
originate at most one press every 6 s; pressing **any** button ignores
incoming broadcasts for 10 s so nobody's selection is overwritten mid-browse.

**Don't want your pattern overwritten?** Hold **Down** for 5 seconds: all
LEDs flash white for half a second, then wireless turns fully off — the badge
keeps its look and ignores (and stops sending) all broadcasts. Press
**RESET** (or power-cycle) to re-enable the contagion.

### Updating the badge

Two layers are installed separately — full details in
[Flashing](#flashing) below:

1. **MicroPython firmware** (the runtime `.bin`): `python flash.py --firmware`
2. **The badge application** (this repo's `src/`): `python flash.py --deploy`

Or both in one pass: `python flash.py --firmware --deploy`.

You will never need to update the MicroPython firmware to use the badge as intended;
you would only need to do that for your own badge hacking projects. So usually only
the second step is needed.

### Patterns & palettes

**Patterns** (`src/patterns.py`):

| Pattern | Body | Eyes |
|---------|------|------|
| `solid` | All body LEDs hold the first palette colour (static) | Steady white |
| `chase` | Palette colours chase along the body | Steady white |
| `twinkle` | Body mostly off; random LEDs flash in palette colours and fade | Slow pulse |
| `wash` | One colour floods across the body, then the next washes over it | Steady white |
| `swap` | Body split into colour blocks that rotate which colour they show | Steady white |
| `breathe` | Whole body fades one colour up/down, advancing colour each breath | Counter-pulse |
| `psychedelic` | Whole body strobes through the palette in unison (all red, all orange, …), ~50 ms per colour | Steady white |

The **eyes** (indices 28 & 30) are never part of the animated body; each pattern
drives them via `leds.set_eyes()`. Default eye colour is white.

**Palettes** (0–10 brightness scale): `rainbow`, `rip`, `ember`, `ghost`,
`blood`, `amethyst`, `halloween`, `toxic`, `ocean`, `sunset`. Add more by
appending to `PALETTES` in `src/patterns.py`.

---

## Prerequisites

### Host machine (your PC)
Install Python 3.11 or higher. Download the code and run:
```
pip install -r requirements.txt
```

This installs:
- `esptool` — flash the MicroPython firmware binary
- `mpremote` — deploy Python source files to the device

### MicroPython firmware

Nothing to do by default: if `firmware/` contains no `.bin`, `flash.py`
automatically downloads a pinned MicroPython build
(`ESP32_GENERIC_C3-20260406-v1.28.0.bin`) into it on the first flash.

To use a different build, download a `.bin` from
https://micropython.org/download/ESP32_GENERIC_C3/ into `firmware/` (the
newest file there wins), or pass its path explicitly with `--firmware PATH`.

---

## Flashing

### 1. Get files

Download the code from this site (either using "Download ZIP" under the code dropdown on
this page, or just git cloning the repo. Make sure Python 3.11 or higher is installed,
and python and pip are on your path. CD into the repo folder and run
```
pip install -r requirements.txt
```
to get the ESP32 tools & drivers.

### 2. Flash MicroPython

This is not normally needed, but if desired for your own badge hacking projects, you
can update the base image and operating system.

Using Python (cross-platform):
```bash
python flash.py --firmware              # auto: newest firmware/*.bin, or download
python flash.py --firmware path/to.bin  # or explicit
```

Writing firmware hard-resets the board, so `flash.py` waits for MicroPython to
reboot — re-detecting the serial port, which can change on re-enumeration —
before deploying. No manual RESET press is usually needed, but if it hangs, just press
RESET.

### 3. Deploy the badge application

```bash
python flash.py --deploy
```

### Flashing many badges in a row

```bash
python flash.py --continuous
```

Batch mode for provisioning a stack of badges with minimal PC interaction:
plug a badge in and it is flashed + deployed automatically; unplug it when
told, plug in the next, repeat. Progress is counted per badge, a failed badge
is reported and skipped (unplug, check it, re-plug to retry), and **Ctrl+C**
ends the session. Firmware is resolved once up front (auto-download included),
so later badges never wait on the network. On a PC with other COM devices,
plug the first badge in *after* starting the command so it is detected as the
newly-appearing port. It is admittedly unlikely anyone but me will ever use
this command, since no one else has a pile of hundreds of badges.

## REPL access (terminal, to see debug output)

```bash
mpremote connect COM3
```

Press **Ctrl+C** to interrupt `main.py` and drop to the REPL.
Press **Ctrl+D** to soft-reset and restart `main.py`.

---

## Project structure

```
esp32c3-firmware/
├── README.md
├── Makefile              # Convenience targets: erase, flash, deploy, all
├── flash.py              # Cross-platform flash/deploy script
├── requirements.txt      # Host dependencies (esptool, mpremote)
├── firmware/
│   └── .gitkeep          # Place MicroPython .bin here
├── src/
│   ├── main.py           # Entry point — wires all modules together
│   ├── buttons.py        # GPIO interrupt + debounce (Up/Down/Left/Right)
│   ├── leds.py           # WS2812B NeoPixel driver (IO10, 44 LEDs + eyes)
│   ├── patterns.py       # Pattern/palette library (two independent axes)
│   └── contagion.py      # ESP-NOW pattern contagion (burst TX, duty-cycled RX)
└── tests/                # Host-side (CPython) unit tests — not deployed to device
    ├── harness.py        # Fake strip/pins/clock/radio + sys.path setup
    ├── test_buttons.py
    ├── test_contagion.py
    ├── test_flash.py
    ├── test_leds.py
    └── test_patterns.py
```

### Running the tests

The `leds`, `patterns`, `buttons`, and `contagion` modules are importable on a
host PC (the MicroPython hardware imports are deferred, and the test harness
fakes `machine`, `micropython`, `network`, `espnow`, and `utime`), so their
logic is covered by plain `unittest`:

```bash
python -B -m unittest discover -s tests
```

(`-B` keeps the source tree free of `__pycache__`. `flash.py --deploy` only ever
ships `src/*.py`, so stray bytecode never reaches the device regardless.)

---

## Module reference

### `buttons`

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

### `leds`

```python
import leds

leds.init()                      # Must call first
leds.set_all(0, 10, 0)           # Fill green, all 44 LEDs (no update yet)
leds.write()                     # Push buffer to hardware
leds.set_all_and_show(0, 0, 10)  # Fill blue + push in one call
leds.set_one(3, 10, 0, 0)        # Set LED index 3 to red
leds.set_range(0, 10, 10, 0, 0)  # Set LEDs 0-9 to dim red
leds.clear_and_show()            # All off

# Body / eye helpers (colours on the 0–10 scale)
leds.set_body_all(0, 10, 0)      # Fill only the body (eyes 28 & 30 untouched)
leds.set_body_logical(0, 10, 0, 0)  # Set the Nth body LED, skipping the eyes
leds.set_eyes(10, 10, 10)        # Set both bat eyes to white
leds.clear_body()                # Body off; eyes untouched
```

Layout constants: `leds.NUM_LEDS` (44), `leds.EYES` (`(28, 30)`),
`leds.BODY` (the 42 non-eye indices), `leds.BODY_COUNT` (42).

### `patterns`

Two independent axes — pattern index and palette index:

```python
import patterns

patterns.pattern_count();  patterns.pattern_name(i)
patterns.palette_count();  patterns.palette_name(j)
patterns.activate(pattern_i, palette_j)      # render initial frame
patterns.tick(pattern_i, palette_j, t_ms)    # advance; no-op for static patterns
```

Changing either axis simply re-calls `activate(...)`, so the running pattern
always reflects the currently selected palette.

### `contagion`

```python
import contagion

contagion.init(pattern_count, palette_count)  # radio up on CHANNEL, reset state

# Every main-loop tick:
infected = contagion.service(t_ms)     # -> (pattern, palette) or None
contagion.broadcast(p, q, t_ms)        # tap: burst our look (False if in cooldown)
contagion.notify_user_activity(t_ms)   # any button press: mute infections 10s
contagion.opt_out()                    # radio hard off until power cycle
contagion.is_enabled()
```

Packet (13 bytes, broadcast to `ff:ff:ff:ff:ff:ff` on WiFi channel 1):
`magic 0xC7 · version · origin MAC (6) · seq (u16) · TTL · pattern · palette`.
Received packets are validated (length/magic/version/TTL/index bounds),
deduplicated by `(origin, seq)` for 60 s, and re-broadcast with TTL−1 after a
0–300 ms jitter while TTL > 1.

**Battery / stability:** the radio stays active for the whole session. The
original design duty-cycled `wlan.active()` at ~1 Hz to save power, but the
~40k driver start/stop cycles per night froze badges (wifi driver
instability), so cycling is disabled pending a gentler scheme; `gc.collect()`
runs once a second to curb heap fragmentation. Senders still repeat each
packet 16× spaced 80 ms — cheap redundancy against loss. Battery impact of
the always-on radio is being measured on hardware (requirement: ≥24 h on the
2000 mAh pack). All timing constants sit at the top of `contagion.py`.
Packets are unauthenticated — anyone with an ESP32 could forge them;
accepted for a conference toy.

---

## Makefile targets

| Target | Description |
|--------|-------------|
| `make help` | Show usage |
| `make erase PORT=...` | Erase device flash |
| `make flash PORT=...` | Erase + flash MicroPython (`FIRMWARE=...` optional, default auto) |
| `make deploy PORT=...` | Copy `src/` to device filesystem |
| `make all PORT=...` | Flash + deploy (`FIRMWARE=...` optional, default auto) |
