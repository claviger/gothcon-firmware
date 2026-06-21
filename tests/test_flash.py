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
                         "ble_scanner.py"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()
