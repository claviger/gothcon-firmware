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
import platform
import subprocess
import sys

CHIP       = "esp32c3"
FLASH_ADDR = "0x0"
BAUD       = 460800


def default_port() -> str:
    system = platform.system()
    if system == "Windows":
        return "COM3"
    elif system == "Darwin":
        return "/dev/tty.usbmodem1"
    else:
        return "/dev/ttyACM0"


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


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Flash MicroPython firmware and deploy source to ESP32-C3."
    )
    ap.add_argument(
        "--port",
        default=default_port(),
        help=f"Serial port (default: {default_port()})",
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

    if args.erase_only:
        erase(args.port, args.baud)
    elif args.firmware:
        erase(args.port, args.baud)
        flash_firmware(args.port, args.baud, args.firmware)

    if args.deploy:
        deploy_src(args.port)

    print("\nDone.")


if __name__ == "__main__":
    main()
