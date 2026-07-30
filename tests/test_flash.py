# test_flash.py — deploy must ship only .py sources, never __pycache__.

import os
import unittest

import harness  # noqa: F401  (sets sys.path)
import flash


class TestSrcFiles(unittest.TestCase):
    def test_returns_only_python_sources(self):
        files = flash.src_files()
        self.assertTrue(files, "expected at least one source file")
        for f in files:
            self.assertTrue(f.endswith(".py"), f)
            self.assertNotIn("__pycache__", f)

    def test_includes_the_known_modules(self):
        names = {os.path.basename(f) for f in flash.src_files()}
        for expected in ("main.py", "leds.py", "patterns.py", "buttons.py",
                         "contagion.py"):
            self.assertIn(expected, names)
        self.assertNotIn("ble_scanner.py", names)   # retired in rev3


class TestResolveFirmware(unittest.TestCase):
    def test_explicit_path_always_wins(self):
        calls = []
        got = flash.resolve_firmware("some/custom.bin", ["firmware/a.bin"],
                                     download=lambda u, d: calls.append(u))
        self.assertEqual(got, "some/custom.bin")
        self.assertEqual(calls, [])                    # no download attempted

    def test_existing_bin_used_without_download(self):
        calls = []
        got = flash.resolve_firmware(None,
                                     ["firmware/ESP32_GENERIC_C3-20251209-v1.27.0.bin",
                                      "firmware/ESP32_GENERIC_C3-20260406-v1.28.0.bin"],
                                     download=lambda u, d: calls.append(u))
        # newest by name (MicroPython names sort by date)
        self.assertEqual(got, "firmware/ESP32_GENERIC_C3-20260406-v1.28.0.bin")
        self.assertEqual(calls, [])

    def test_empty_firmware_dir_downloads_pinned_url(self):
        calls = []
        def fake_download(u, d):
            calls.append((u, d))
            return True
        got = flash.resolve_firmware(None, [], download=fake_download)
        self.assertEqual(len(calls), 1)
        url, dest = calls[0]
        self.assertEqual(url, flash.FIRMWARE_URL)
        self.assertTrue(dest.endswith("ESP32_GENERIC_C3-20260406-v1.28.0.bin"))
        self.assertEqual(got, dest)

    def test_auto_keyword_behaves_like_omitted(self):
        got = flash.resolve_firmware("auto", ["firmware/only.bin"],
                                     download=lambda u, d: self.fail("no download"))
        self.assertEqual(got, "firmware/only.bin")

    def test_failed_download_resolves_to_none(self):
        # Offline: auto-resolution reports "nothing to flash" instead of raising.
        got = flash.resolve_firmware(None, [], download=lambda u, d: False)
        self.assertIsNone(got)


class _FakeResponse:
    """Context-managed fake for urllib's response object."""

    def __init__(self, chunks, fail_after=None):
        self._chunks = list(chunks)
        self._fail_after = fail_after
        self._reads = 0

    def read(self, n):
        if self._fail_after is not None and self._reads >= self._fail_after:
            raise OSError("connection reset")
        self._reads += 1
        return self._chunks.pop(0) if self._chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestDownloadFirmware(unittest.TestCase):
    def test_success_writes_dest_atomically(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "fw.bin")
            ok = flash._download_firmware(
                "http://x/fw.bin", dest,
                opener=lambda u: _FakeResponse([b"abc", b"def"]))
            self.assertTrue(ok)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), b"abcdef")
            self.assertEqual(os.listdir(tmp), ["fw.bin"])   # no .part left

    def test_failure_leaves_no_partial_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "fw.bin")
            ok = flash._download_firmware(
                "http://x/fw.bin", dest,
                opener=lambda u: _FakeResponse([b"abc"], fail_after=1))
            self.assertFalse(ok)
            self.assertEqual(os.listdir(tmp), [])           # dest AND .part gone

    def test_creates_missing_destination_directory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "not", "yet", "here", "fw.bin")
            ok = flash._download_firmware(
                "http://x/fw.bin", dest,
                opener=lambda u: _FakeResponse([b"abc"]))
            self.assertTrue(ok)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), b"abc")

    def test_unreachable_host_fails_cleanly(self):
        import tempfile
        def no_route(url):
            raise OSError("no route to host")
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "fw.bin")
            self.assertFalse(flash._download_firmware("http://x/fw.bin", dest,
                                                      opener=no_route))
            self.assertEqual(os.listdir(tmp), [])


class TestResolvePort(unittest.TestCase):
    def test_explicit_port_always_wins(self):
        self.assertEqual(flash.resolve_port("COM7", ["COM3", "COM4"]), "COM7")

    def test_single_available_port_is_auto_selected(self):
        self.assertEqual(flash.resolve_port(None, ["COM13"]), "COM13")

    def test_no_ports_raises(self):
        with self.assertRaises(ValueError):
            flash.resolve_port(None, [])

    def test_multiple_ports_without_explicit_raises(self):
        with self.assertRaises(ValueError):
            flash.resolve_port(None, ["COM3", "COM4"])


class TestAvailablePorts(unittest.TestCase):
    """Only USB-backed serial devices count — platform UARTs like the
    Raspberry Pi's always-present /dev/ttyAMA0 must not appear as badges."""

    class _Port:
        def __init__(self, device, vid):
            self.device = device
            self.vid = vid

    def test_filters_out_non_usb_platform_uarts(self):
        fake = [self._Port("/dev/ttyAMA0", None),        # Pi on-board UART
                self._Port("/dev/ttyACM0", 0x303A)]      # badge (Espressif)
        got = flash.available_ports(comports=lambda: fake)
        self.assertEqual(got, ["/dev/ttyACM0"])

    def test_empty_when_only_platform_uarts_exist(self):
        fake = [self._Port("/dev/ttyAMA0", None)]
        self.assertEqual(flash.available_ports(comports=lambda: fake), [])


class TestContinuousWaits(unittest.TestCase):
    """Port-watching primitives for --continuous batch flashing."""

    @staticmethod
    def scripted(*snapshots):
        """list_ports fake yielding successive port-list snapshots."""
        seq = list(snapshots)
        return lambda: seq.pop(0) if len(seq) > 1 else seq[0]

    def test_wait_for_new_port_returns_the_appeared_port(self):
        naps = []
        got = flash.wait_for_new_port(set(), list_ports=self.scripted([], [], ["COM5"]),
                                      sleep=naps.append)
        self.assertEqual(got, "COM5")
        self.assertEqual(len(naps), 2)          # polled twice before it appeared

    def test_wait_for_new_port_ignores_baseline_ports(self):
        got = flash.wait_for_new_port({"COM3"},
                                      list_ports=self.scripted(["COM3"], ["COM3", "COM7"]),
                                      sleep=lambda s: None)
        self.assertEqual(got, "COM7")

    def test_wait_for_disconnect_returns_once_port_vanishes(self):
        naps = []
        flash.wait_for_disconnect("COM5",
                                  list_ports=self.scripted(["COM5"], ["COM5"], []),
                                  sleep=naps.append)
        self.assertEqual(len(naps), 2)


class TestReadyPort(unittest.TestCase):
    def test_explicit_port_used_when_present(self):
        self.assertEqual(flash._ready_port("COM5", ["COM5", "COM6"]), "COM5")

    def test_explicit_port_absent_means_not_ready(self):
        self.assertIsNone(flash._ready_port("COM5", ["COM6"]))

    def test_single_port_auto_selected(self):
        self.assertEqual(flash._ready_port(None, ["COM9"]), "COM9")

    def test_no_ports_not_ready(self):
        self.assertIsNone(flash._ready_port(None, []))

    def test_ambiguous_ports_not_ready(self):
        self.assertIsNone(flash._ready_port(None, ["COM9", "COM10"]))


class TestWaitForMicropython(unittest.TestCase):
    def test_returns_port_once_repl_responds(self):
        port = flash.wait_for_micropython(
            None, timeout=5, probe=lambda p: True, list_ports=lambda: ["COM9"])
        self.assertEqual(port, "COM9")

    def test_times_out_when_device_never_comes_up(self):
        with self.assertRaises(TimeoutError):
            flash.wait_for_micropython(
                None, timeout=0, probe=lambda p: False, list_ports=lambda: [])


if __name__ == "__main__":
    unittest.main()
