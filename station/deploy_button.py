#!/usr/bin/env python3
"""Badge flashing station: PiTFT tactile buttons drive flash.py.

Runs on the Raspberry Pi provisioning station (Pi 2 + Adafruit 2.8"
capacitive PiTFT, console on the TFT). Plug a badge in, press a button:

    button 1  (GPIO 23)  ->  python flash.py --deploy
    button 2  (GPIO 22)  ->  python flash.py --firmware --deploy
    button 3  (GPIO 27)  ->  hold 2s: sudo poweroff (safe shutdown)
    button 4  (GPIO 18)  ->  (spare; on this board GPIO18 doubles as the
                              backlight jumper, so it's left unmapped)

Wiring differs by board generation: the ORIGINAL 2.8" PiTFT (this station's
board) wires its switches to GPIO 23/22/27(21 on the oldest revs)/18; the
later "Plus" boards use GPIO 17/22/23/27. If a button lands wrong, edit the
constants below — the startup banner prints the live mapping.

Pi-only: requires gpiozero (preinstalled on Raspberry Pi OS). Not part of
the firmware test suite. Ctrl+C exits.
"""

import queue
import subprocess
import sys
from pathlib import Path

from gpiozero import Button

# --- button map (see module docstring) --------------------------------------
BTN_DEPLOY     = 23   # button 1: deploy src/ to the badge (the common case)
BTN_FULL_FLASH = 22   # button 2: erase + MicroPython + deploy (unknown badges)
BTN_SHUTDOWN   = 27   # button 3: hold 2s to power the station off
BTN_SPARE      = 18   # button 4: unmapped (backlight jumper pin on this board)

SHUTDOWN_HOLD_S = 2

FLASH_PY = Path(__file__).resolve().parent.parent / "flash.py"

_jobs = queue.Queue(maxsize=1)   # presses during a running job are dropped


def _request(action):
    def handler():
        try:
            _jobs.put_nowait(action)
        except queue.Full:
            pass                 # a job is already running/queued — ignore
    return handler


def _run_flash(*args) -> None:
    cmd = [sys.executable, str(FLASH_PY), *args]
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\n*** SUCCESS ***", flush=True)
    else:
        print(f"\n*** FAILED (exit {result.returncode}) — check the badge, "
              "then press again ***", file=sys.stderr, flush=True)


def main() -> None:
    deploy = Button(BTN_DEPLOY, pull_up=True, bounce_time=0.05)
    full   = Button(BTN_FULL_FLASH, pull_up=True, bounce_time=0.05)
    power  = Button(BTN_SHUTDOWN, pull_up=True, bounce_time=0.05,
                    hold_time=SHUTDOWN_HOLD_S)

    deploy.when_pressed = _request("deploy")
    full.when_pressed   = _request("full")
    # Shutdown requires a deliberate hold so a bump can't kill the station.
    power.when_pressed  = lambda: print(
        f"(hold {SHUTDOWN_HOLD_S}s to shut down)", flush=True)
    power.when_held     = _request("shutdown")

    print("=" * 40)
    print("Badge flashing station")
    print(f"  button 1 (GPIO {BTN_DEPLOY}): deploy badge app")
    print(f"  button 2 (GPIO {BTN_FULL_FLASH}): full flash + deploy")
    print(f"  button 3 (GPIO {BTN_SHUTDOWN}): hold {SHUTDOWN_HOLD_S}s = shutdown")
    print("=" * 40)

    while True:
        print("\n=== READY — plug in a badge, then press a button ===",
              flush=True)
        action = _jobs.get()
        if action == "deploy":
            _run_flash("--deploy")
        elif action == "full":
            _run_flash("--firmware", "--deploy")
        elif action == "shutdown":
            print("\nShutting down the station...", flush=True)
            # First user on Raspberry Pi OS has passwordless sudo by default.
            subprocess.run(["sudo", "poweroff"])
            return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye")
