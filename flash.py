#!/usr/bin/env python3
"""
Cross-platform flash helper for ESP32-C3 MicroPython.

Usage:
    python flash.py --port COM3 --firmware firmware/micropython.bin
    python flash.py --erase-only --port /dev/ttyACM0
    python flash.py --port COM3 --deploy
    python flash.py --port COM3 --firmware firmware/micropython.bin --deploy
"""

import argparse
import glob
import os
import subprocess
import sys
import time

CHIP       = "esp32c3"
FLASH_ADDR = "0x0"
BAUD       = 460800

# After a firmware flash the board hard-resets and re-enumerates its USB CDC,
# which takes a few seconds (and can change the COM number). Poll for the
# MicroPython REPL rather than deploying blindly into a mid-reboot device.
READY_TIMEOUT_S  = 30
PROBE_INTERVAL_S = 0.5


def available_ports() -> list:
    """Serial port device names present on the system (via pyserial)."""
    from serial.tools import list_ports
    return sorted(p.device for p in list_ports.comports())


def resolve_port(explicit, available) -> str:
    """Choose which serial port to use.

    An explicit --port always wins. Otherwise auto-select when exactly one port
    is present; raise a clear error when there are none or several so we never
    guess and flash the wrong device.
    """
    if explicit:
        return explicit
    if len(available) == 1:
        return available[0]
    if not available:
        raise ValueError("no serial ports found - plug in the device or pass --port")
    raise ValueError(
        "multiple serial ports found ({}) - choose one with --port".format(
            ", ".join(available)))


def run(cmd: list) -> None:
    print("$", " ".join(str(c) for c in cmd))
    sys.stdout.flush()
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}", file=sys.stderr)
        sys.stderr.flush()
        sys.exit(result.returncode)


def erase(port: str, baud: int) -> None:
    print(f"\n--- Erasing flash on {port} ---")
    run([
        "esptool",
        "--chip", CHIP,
        "--port", port,
        "--baud", str(baud),
        "erase-flash",
    ])


def flash_firmware(port: str, baud: int, firmware_path: str) -> None:
    print(f"\n--- Writing firmware: {firmware_path} ---")
    run([
        "esptool",
        "--chip", CHIP,
        "--port", port,
        "--baud", str(baud),
        "write-flash",
        "-z", FLASH_ADDR,
        firmware_path,
    ])


def src_files() -> list:
    """Python source files under src/ to deploy — never __pycache__/build junk.

    Anchored to this script's directory so it works regardless of CWD.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return sorted(glob.glob(os.path.join(here, "src", "*.py")))


def deploy_src(port: str) -> None:
    """Copy the src/ Python sources to the device filesystem root using mpremote."""
    files = src_files()
    print(f"\n--- Deploying {len(files)} source file(s) to device on {port} ---")
    run([sys.executable, "-m", "mpremote", "connect", port, "cp"] + files + [":"])


def _ready_port(explicit, available):
    """Which port to probe right now, or None if the device isn't back yet.

    Mirrors resolve_port's preference (explicit wins, else a lone port) but
    returns None instead of raising while we're still waiting for the reboot.
    """
    if explicit:
        return explicit if explicit in available else None
    return available[0] if len(available) == 1 else None


def _probe_micropython(port) -> bool:
    """True if a MicroPython REPL answers on `port` (board booted and ready)."""
    result = subprocess.run(
        [sys.executable, "-m", "mpremote", "connect", port, "exec", "pass"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def wait_for_micropython(explicit, timeout=READY_TIMEOUT_S,
                         probe=_probe_micropython, list_ports=None) -> str:
    """Wait for the board to reboot into MicroPython after a firmware flash.

    Re-detects the (possibly renumbered) port and returns it as soon as the
    REPL responds. Raises TimeoutError if the device never comes up.
    """
    if list_ports is None:
        list_ports = available_ports
    print("\n--- Waiting for the board to reboot into MicroPython ---")
    deadline = time.monotonic() + timeout
    while True:
        port = _ready_port(explicit, list_ports())
        if port and probe(port):
            print(f"    MicroPython is up on {port}")
            return port
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "board did not present a MicroPython REPL within {}s "
                "(press RESET, or run --deploy on its own once it boots)".format(timeout))
        time.sleep(PROBE_INTERVAL_S)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Flash MicroPython firmware and deploy source to ESP32-C3."
    )
    ap.add_argument(
        "--port",
        default=None,
        help="Serial port (default: auto-detect when exactly one port is present)",
    )
    ap.add_argument(
        "--firmware",
        default=None,
        metavar="PATH",
        help="Path to MicroPython .bin to flash (triggers erase + write)",
    )
    ap.add_argument(
        "--baud",
        type=int,
        default=BAUD,
        help=f"Baud rate for esptool (default: {BAUD})",
    )
    ap.add_argument(
        "--erase-only",
        action="store_true",
        help="Erase flash without writing firmware",
    )
    ap.add_argument(
        "--deploy",
        action="store_true",
        help="Copy src/ to device filesystem after flash (uses mpremote)",
    )
    args = ap.parse_args()

    if not args.firmware and not args.erase_only and not args.deploy:
        ap.print_help()
        sys.exit(0)

    try:
        port = resolve_port(args.port, available_ports())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"Using serial port: {port}")

    if args.erase_only:
        erase(port, args.baud)
    elif args.firmware:
        erase(port, args.baud)
        flash_firmware(port, args.baud, args.firmware)

    if args.deploy:
        if args.firmware:
            # The board just hard-reset from the flash; wait for MicroPython to
            # come back (re-detecting the port) before deploying into it.
            try:
                port = wait_for_micropython(args.port)
            except TimeoutError as exc:
                print(f"error: {exc}", file=sys.stderr)
                sys.exit(1)
        deploy_src(port)

    print("\nDone.")


if __name__ == "__main__":
    main()
