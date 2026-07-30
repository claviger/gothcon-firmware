#!/usr/bin/env python3
"""Badge flashing station: PiTFT tactile buttons drive flash.py.

Runs on the Raspberry Pi provisioning station (Pi 2 + Adafruit 2.8"
capacitive PiTFT, console on the TFT). Plug a badge in, press a button:

    top button     (GPIO 17)  ->  python flash.py --deploy
    second button  (GPIO 22)  ->  python flash.py --firmware --deploy
    third button   (GPIO 23)  ->  (spare, unmapped)
    bottom button  (GPIO 27)  ->  hold 2s: sudo poweroff (safe shutdown)

The PiTFT's four switches are wired active-low to GPIO 17/22/23/27. If your
board's physical order differs, just edit the constants below — the startup
banner prints the live mapping.

Pi-only: requires gpiozero (preinstalled on Raspberry Pi OS). Not part of
the firmware test suite. Ctrl+C exits.
"""

import queue
import subprocess
import sys
from pathlib import Path

from gpiozero import Button

# --- button map (see module docstring) --------------------------------------
BTN_DEPLOY     = 17   # top:    deploy src/ to the badge (the common case)
BTN_FULL_FLASH = 22   # second: erase + MicroPython + deploy (unknown badges)
BTN_SPARE      = 23   # third:  unmapped
BTN_SHUTDOWN   = 27   # bottom: hold 2s to power the station off

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
    print(f"  GPIO {BTN_DEPLOY} (top):    deploy badge app")
    print(f"  GPIO {BTN_FULL_FLASH} (2nd):    full flash + deploy")
    print(f"  GPIO {BTN_SHUTDOWN} (bottom): hold {SHUTDOWN_HOLD_S}s = shutdown")
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
