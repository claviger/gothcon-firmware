# ESP32-C3 MicroPython Firmware

MicroPython firmware for an ESP32-C3 with:
- Interrupt-driven pushbuttons on IO0, IO2, IO3, IO4
- 44 WS2812B (NeoPixel) addressable RGB LEDs on IO10 — including two "bat eye"
  LEDs (indices **29** and **31**) driven independently of the animated body
- A library of colour-agnostic **patterns** combined with selectable **palettes**
- BLE active scanner capturing SCAN_RSP packets

---

## Hardware

| GPIO | Function |
|------|----------|
| IO0  | Button (BOOT button, active-low, internal pull-up) |
| IO2  | Button (active-low, internal pull-up) |
| IO3  | Button (active-low, internal pull-up) |
| IO4  | Button (active-low, internal pull-up) |
| IO10 | WS2812B data line (44 LEDs daisy-chained; eyes at indices 29 & 31) |

**LED power warning**: 44 LEDs at full white draw ~2.6A. Use a dedicated
5V supply for the LED strip and share GND with the ESP32-C3. Do not power
the strip from the MCU's onboard regulator. For USB-powered prototyping,
keep brightness values ≤ 64 per channel.

---

## Controls & visual patterns

The badge shows one **pattern** rendered with one **palette**. The two are
independent axes — any pattern can be combined with any palette at runtime.

| Button | Action |
|--------|--------|
| IO0 (BOOT) | Previous pattern |
| IO2 | Next pattern |
| IO3 | Next palette |
| IO4 | Toggle BLE scan (solid blue while scanning; pattern resumes on stop) |

**Patterns** (`src/patterns.py`):

| Pattern | Body | Eyes |
|---------|------|------|
| `solid` | All body LEDs hold the first palette colour (static) | Steady white |
| `chase` | Palette colours chase along the body | Steady white |
| `twinkle` | Body mostly off; random LEDs flash in palette colours and fade | Slow pulse |
| `wash` | One colour floods across the body, then the next washes over it | Steady white |
| `swap` | Body split into colour blocks that rotate which colour they show | Steady white |
| `breathe` | Whole body fades one colour up/down, advancing colour each breath | Counter-pulse |

The **eyes** (indices 29 & 31) are never part of the animated body; each pattern
drives them via `leds.set_eyes()`. Default eye colour is white.

**Palettes** (0–10 brightness scale): `rainbow`, `rip`, `ember`, `ghost`,
`blood`, `amethyst`. Add more by appending to `PALETTES` in `src/patterns.py`.

---

## Prerequisites

### Host machine (your PC)
```
pip install -r requirements.txt
```

This installs:
- `esptool` — flash the MicroPython firmware binary
- `mpremote` — deploy Python source files to the device

### MicroPython firmware

1. Visit: https://micropython.org/download/ESP32_GENERIC_C3/
2. Download the latest stable `.bin` file
   (e.g. `ESP32_GENERIC_C3-20240602-v1.23.0.bin`)
3. Place it in the `firmware/` directory

---

## Flashing

### 1. Find your serial port

**Windows**: Open Device Manager → Ports (COM & LPT). Look for:
- `USB Serial Device (COMx)` — built-in USB CDC on ESP32-C3
- `CH340 / CH343 (COMx)` — external USB-serial bridge

**Linux**: `ls /dev/ttyACM*` or `ls /dev/ttyUSB*`

**macOS**: `ls /dev/tty.usbmodem*`

### 2. Put the ESP32-C3 in download mode (if needed)

Hold **IO0 (BOOT)** while pressing **RESET**, then release RESET.
On most boards `esptool` triggers download mode automatically.

### 3. Flash MicroPython

Using `make` (requires GNU Make — available in Git Bash, WSL, or Chocolatey):
```bash
make flash PORT=COM3 FIRMWARE=firmware/ESP32_GENERIC_C3-v1.23.0.bin
```

Using Python directly (cross-platform):
```bash
python flash.py --port COM3 --firmware firmware/ESP32_GENERIC_C3-v1.23.0.bin
```

### 4. Deploy source files

```bash
make deploy PORT=COM3
```
or
```bash
python flash.py --port COM3 --deploy
```

### 5. Flash + deploy in one step

```bash
make all PORT=COM3 FIRMWARE=firmware/ESP32_GENERIC_C3-v1.23.0.bin
```

---

## REPL access

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
│   ├── buttons.py        # GPIO interrupt + debounce (IO0/2/3/4)
│   ├── leds.py           # WS2812B NeoPixel driver (IO10, 44 LEDs + eyes)
│   ├── patterns.py       # Pattern/palette library (two independent axes)
│   └── ble_scanner.py    # BLE active scan + SCAN_RSP capture
└── tests/                # Host-side (CPython) unit tests — not deployed to device
    ├── harness.py        # FakeStrip + fake utime + sys.path setup
    ├── test_leds.py
    └── test_patterns.py
```

### Running the tests

The `leds` and `patterns` modules are importable on a host PC (the MicroPython
hardware imports are deferred), so their logic is covered by plain `unittest`:

```bash
python -m unittest discover -s tests
```

---

## Module reference

### `buttons`

```python
import buttons

def my_callback(pin_num):
    print(f"GPIO {pin_num} pressed")

# Register all four buttons at once
buttons.register_all(cb_io0, cb_io2, cb_io3, cb_io4)

# Or register individually
buttons.register(2, my_callback)
buttons.unregister(2)
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
leds.set_body_all(0, 10, 0)      # Fill only the body (eyes 29 & 31 untouched)
leds.set_body_logical(0, 10, 0, 0)  # Set the Nth body LED, skipping the eyes
leds.set_eyes(10, 10, 10)        # Set both bat eyes to white
leds.clear_body()                # Body off; eyes untouched
```

Layout constants: `leds.NUM_LEDS` (44), `leds.EYES` (`(29, 31)`),
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

### `ble_scanner`

```python
import ble_scanner

ble_scanner.init()  # Power on BLE radio

# With callback (fires for each SCAN_RSP packet):
def on_rsp(addr_type, addr, rssi, adv_data):
    name = ble_scanner.parse_ad_structures(adv_data).get(0x09, b'')
    print(ble_scanner.format_addr(addr), rssi, name)

ble_scanner.start_scan(on_scan_rsp=on_rsp)

# Without callback — accumulates results:
ble_scanner.start_scan()
# ... wait ...
ble_scanner.stop_scan()
for rec in ble_scanner.get_results():
    print(rec)
```

---

## Makefile targets

| Target | Description |
|--------|-------------|
| `make help` | Show usage |
| `make erase PORT=...` | Erase device flash |
| `make flash PORT=... FIRMWARE=...` | Erase + flash MicroPython |
| `make deploy PORT=...` | Copy `src/` to device filesystem |
| `make all PORT=... FIRMWARE=...` | Flash + deploy |
