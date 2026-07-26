# test_contagion.py — ESP-NOW contagion protocol: packet format, dedup,
# cooldowns, interaction mute, TTL/relay, burst + listen-window scheduling.

import os
import random
import re
import unittest

import harness  # noqa: F401  (sets sys.path, installs fake utime/machine/network/espnow)
from harness import FakeWLAN, FakeESPNow
import contagion

PC, QC = 7, 10               # pattern/palette counts injected in tests
MAC_A = b"\xaa\xaa\xaa\xaa\xaa\x01"
MAC_B = b"\xbb\xbb\xbb\xbb\xbb\x02"


def pkt(origin=MAC_A, seq=1, ttl=3, pattern=2, palette=5):
    return contagion.pack(origin, seq, ttl, pattern, palette)


class TestMainIntegration(unittest.TestCase):
    def test_every_contagion_reference_in_main_exists(self):
        """main.py can't be imported by tests (infinite loop), so statically
        verify every `contagion.<name>` it references actually exists —
        a missing constant otherwise only crashes on the badge."""
        main_path = os.path.join(os.path.dirname(__file__), "..", "src", "main.py")
        with open(main_path) as f:
            source = f.read()
        names = set(re.findall(r"\bcontagion\.(\w+)", source))
        self.assertTrue(names, "expected main.py to use the contagion module")
        for name in sorted(names):
            self.assertTrue(hasattr(contagion, name),
                            "main.py references contagion.%s which does not exist" % name)


class TestPackUnpack(unittest.TestCase):
    def test_roundtrip(self):
        data = contagion.pack(MAC_A, 513, 3, 6, 9)
        self.assertEqual(len(data), 13)
        self.assertEqual(contagion.unpack(data, PC, QC), (MAC_A, 513, 3, 6, 9))

    def test_rejects_wrong_length(self):
        self.assertIsNone(contagion.unpack(pkt()[:-1], PC, QC))   # short
        self.assertIsNone(contagion.unpack(pkt() + b"\x00", PC, QC))  # long

    def test_rejects_bad_magic_and_version(self):
        bad_magic = b"\x00" + pkt()[1:]
        self.assertIsNone(contagion.unpack(bad_magic, PC, QC))
        bad_ver = pkt()[:1] + b"\x7f" + pkt()[2:]
        self.assertIsNone(contagion.unpack(bad_ver, PC, QC))

    def test_rejects_bad_ttl(self):
        self.assertIsNone(contagion.unpack(pkt(ttl=0), PC, QC))
        self.assertIsNone(
            contagion.unpack(pkt(ttl=contagion.TTL_INITIAL + 1), PC, QC))

    def test_rejects_out_of_range_indices(self):
        self.assertIsNone(contagion.unpack(pkt(pattern=PC), PC, QC))
        self.assertIsNone(contagion.unpack(pkt(palette=QC), PC, QC))


class _Radio(unittest.TestCase):
    """Base: contagion initialised against fresh fakes, deterministic RNG."""

    def setUp(self):
        random.seed(42)
        contagion.init(PC, QC)
        self.wlan = FakeWLAN.last
        self.now = FakeESPNow.last

    def rx(self, payload, sender=MAC_A):
        self.now.rx_queue.append((sender, payload))

    def run_until(self, start, end, step=10):
        """Drive service() over [start, end); return list of (t, result)."""
        events = []
        t = start
        while t < end:
            r = contagion.service(t)
            if r is not None:
                events.append((t, r))
            t += step
        return events


class TestInitAndScheduler(_Radio):
    def test_init_brings_radio_up_on_pinned_channel(self):
        self.assertIn(("disconnect",), self.wlan.call_log)
        self.assertEqual(self.wlan.channel, contagion.CHANNEL)
        self.assertIn(b"\xff" * 6, self.now.peers)
        self.assertTrue(contagion.is_enabled())

    def test_radio_on_during_listen_window_off_outside(self):
        contagion.service(10_000)          # phase 0 — inside window
        self.assertTrue(self.wlan.is_active)
        contagion.service(10_000 + contagion.LISTEN_MS + 50)   # outside
        self.assertFalse(self.wlan.is_active)
        contagion.service(11_000)          # next window
        self.assertTrue(self.wlan.is_active)

    def test_radio_held_on_during_burst_outside_window(self):
        contagion.broadcast(1, 1, 10_000)
        contagion.service(10_000 + contagion.LISTEN_MS + 50)   # burst active
        self.assertTrue(self.wlan.is_active)

    def test_constants_invariant_burst_covers_listen_period(self):
        span = contagion.BURST_REPEATS * contagion.BURST_SPACING_MS
        self.assertGreater(span, contagion.LISTEN_PERIOD_MS)
        self.assertLess(contagion.BURST_SPACING_MS, contagion.LISTEN_MS)


class TestBroadcast(_Radio):
    def test_broadcast_emits_full_burst(self):
        self.assertTrue(contagion.broadcast(3, 4, 10_000))
        self.run_until(10_000, 13_000)
        self.assertEqual(len(self.now.sent), contagion.BURST_REPEATS)
        peer, payload = self.now.sent[0]
        self.assertEqual(peer, b"\xff" * 6)
        origin, seq, ttl, pattern, palette = contagion.unpack(payload, PC, QC)
        self.assertEqual(origin, FakeWLAN.MAC)
        self.assertEqual((ttl, pattern, palette), (contagion.TTL_INITIAL, 3, 4))

    def test_local_cooldown_blocks_rapid_taps(self):
        self.assertTrue(contagion.broadcast(1, 1, 10_000))
        self.assertFalse(contagion.broadcast(1, 1, 10_000 + contagion.COOLDOWN_MS - 1))
        self.assertTrue(contagion.broadcast(1, 1, 10_000 + 2 * contagion.COOLDOWN_MS))

    def test_seq_increments_per_broadcast(self):
        contagion.broadcast(1, 1, 10_000)
        self.run_until(10_000, 13_000)
        first_seq = contagion.unpack(self.now.sent[0][1], PC, QC)[1]
        self.now.sent.clear()
        contagion.broadcast(1, 1, 30_000)
        self.run_until(30_000, 33_000)
        second_seq = contagion.unpack(self.now.sent[0][1], PC, QC)[1]
        self.assertEqual(second_seq, first_seq + 1)


class TestReceive(_Radio):
    def test_infection_applied_once_then_deduped(self):
        self.rx(pkt(seq=7))
        self.assertEqual(contagion.service(10_000), (2, 5))
        self.rx(pkt(seq=7))                       # same press replayed
        self.assertIsNone(contagion.service(11_000))

    def test_dedup_entry_expires(self):
        self.rx(pkt(seq=7))
        self.assertEqual(contagion.service(10_000), (2, 5))
        t = 10_000 + contagion.DEDUP_TTL_MS + contagion.COOLDOWN_MS + 1_000
        t -= t % contagion.LISTEN_PERIOD_MS       # align to a listen window
        self.rx(pkt(seq=7))
        self.assertEqual(contagion.service(t), (2, 5))

    def test_per_origin_cooldown(self):
        self.rx(pkt(seq=1))
        self.assertEqual(contagion.service(10_000), (2, 5))
        self.rx(pkt(seq=2, pattern=3))            # new press, same origin, too soon
        self.assertIsNone(contagion.service(10_000 + 1_000))
        self.rx(pkt(seq=3, pattern=3))
        t = 10_000 + contagion.COOLDOWN_MS + 1_000
        self.assertEqual(contagion.service(t), (3, 5))

    def test_own_packets_ignored(self):
        self.rx(pkt(origin=FakeWLAN.MAC))
        self.assertIsNone(contagion.service(10_000))

    def test_garbage_ignored(self):
        self.rx(b"not a packet")
        self.assertIsNone(contagion.service(10_000))


class TestRelay(_Radio):
    def test_relay_decrements_ttl_with_bounded_jitter(self):
        self.rx(pkt(ttl=3, seq=9))
        self.assertEqual(contagion.service(10_000), (2, 5))
        self.run_until(10_010, 10_010 + contagion.RELAY_JITTER_MAX_MS + 200)
        self.assertGreaterEqual(len(self.now.sent), 1)
        origin, seq, ttl, _, _ = contagion.unpack(self.now.sent[0][1], PC, QC)
        self.assertEqual((origin, seq, ttl), (MAC_A, 9, 2))   # origin preserved, TTL-1

    def test_ttl_1_applies_but_never_relays(self):
        self.rx(pkt(ttl=1, seq=9))
        self.assertEqual(contagion.service(10_000), (2, 5))
        self.run_until(10_010, 14_000)
        self.assertEqual(self.now.sent, [])


class TestMute(_Radio):
    def test_button_activity_mutes_infections(self):
        contagion.notify_user_activity(10_000)
        self.rx(pkt(seq=5))
        self.assertIsNone(contagion.service(11_000))          # muted
        # not dedup-recorded while muted: the same press works after expiry
        t = 10_000 + contagion.INTERACTION_MUTE_MS + 1_000
        t -= t % contagion.LISTEN_PERIOD_MS
        self.rx(pkt(seq=5))
        self.assertEqual(contagion.service(t), (2, 5))


class TestOptOut(_Radio):
    def test_opt_out_silences_everything(self):
        contagion.opt_out()
        self.assertFalse(contagion.is_enabled())
        self.assertFalse(self.wlan.is_active)
        calls_before = list(self.wlan.call_log)
        self.rx(pkt())
        self.assertIsNone(contagion.service(10_000))
        self.assertFalse(contagion.broadcast(1, 1, 20_000))
        self.assertEqual(self.now.sent, [])
        self.assertEqual(self.wlan.call_log, calls_before)    # radio never touched again


if __name__ == "__main__":
    unittest.main()
