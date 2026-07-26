# contagion.py — ESP-NOW pattern "contagion" for the badge
#
# Tap Down and nearby badges adopt your (pattern, palette), cascading outward
# a few hops so the change sweeps the room in ~1s-per-hop waves. See README.
#
# Design notes:
#   * Transport is ESP-NOW broadcast (ff:ff:ff:ff:ff:ff) on a pinned WiFi
#     channel — connectionless, ~1ms airtime, loss-tolerant by design.
#   * Radio: stays active for the whole session. The original design duty-
#     cycled wlan.active() at ~1Hz to save battery, but ~40k driver start/stop
#     cycles overnight froze badges (wifi driver instability / heap
#     fragmentation), so cycling is disabled until a gentler scheme is proven.
#     Senders still repeat each packet as a BURST — cheap redundancy against
#     loss, and required again if duty-cycling ever returns.
#   * gc.collect() runs once per LISTEN_PERIOD_MS to curb heap fragmentation
#     from per-tick allocations on long uptimes.
#   * This module never imports patterns/leds — it deals purely in indices;
#     main.py owns applying them. No ISR/irq callbacks: main.py's loop calls
#     service(t_ms) every tick and we poll recv with a zero timeout.
#   * Packets are unauthenticated: anyone with an ESP32 can forge them.
#     Accepted for a conference toy; bounds checks + cooldowns cap the blast
#     radius.
#
# Host tests fake `network`/`espnow` (see tests/harness.py); the imports are
# deferred into init() like leds.py so the pure helpers need no radio at all.

import gc
import struct
import random
import utime

# --- tunable constants (expected to be tuned on real hardware) --------------
CHANNEL             = 1        # all badges must share this WiFi channel
LISTEN_MS           = 150      # (unused while duty-cycling is disabled — kept
LISTEN_PERIOD_MS    = 1000     #  with the burst invariant for its possible
                               #  return; period also paces gc.collect())
BURST_REPEATS       = 16       # copies of each packet sent per burst
BURST_SPACING_MS    = 80       # gap between copies (span 1.28s > listen period)
TTL_INITIAL         = 3        # hop depth: origin + ~3 hops of cascade
COOLDOWN_MS         = 6000     # min gap between presses (local and per-origin)
DEDUP_TTL_MS        = 60_000   # how long a (origin, seq) id is remembered
RELAY_JITTER_MAX_MS = 300      # random relay delay to avoid collision storms
INTERACTION_MUTE_MS = 10_000   # ignore infections after any local button press
OPTOUT_HOLD_MS      = 5000     # hold Down this long to opt out of wireless
OPTOUT_FLASH_MS     = 500      # white confirmation flash on opt-out

_MAGIC   = 0xC7
_VERSION = 0x01
_FMT     = ">BB6sHBBB"         # magic, version, origin mac, seq, ttl, pattern, palette
_PKT_LEN = struct.calcsize(_FMT)   # 13
_BCAST   = b"\xff" * 6

# --- module state -----------------------------------------------------------
_wlan    = None
_espnow  = None
_enabled = False
_mac     = b"\x00" * 6
_last_gc_ms = None             # paces the periodic gc.collect()
_counts  = (0, 0)              # (pattern_count, palette_count)
_seq     = 0
_last_broadcast_ms = None      # local tap cooldown
_mute_until_ms     = None      # interaction mute deadline
_dedup       = {}              # (origin, seq) -> expiry ticks
_origin_last = {}              # origin -> last accepted ticks
_burst       = None            # {"payload": bytes, "next_ms": t, "remaining": n}


# --- pure protocol helpers (host-testable without any radio) ----------------

def pack(origin: bytes, seq: int, ttl: int, pattern: int, palette: int) -> bytes:
    """Encode a contagion packet (13 bytes)."""
    return struct.pack(_FMT, _MAGIC, _VERSION, origin, seq, ttl, pattern, palette)


def unpack(data, pattern_count: int, palette_count: int):
    """Decode + validate a packet. Returns (origin, seq, ttl, pattern, palette)
    or None if the packet is malformed, from a wrong protocol, or out of range.
    """
    if data is None or len(data) != _PKT_LEN:
        return None
    magic, version, origin, seq, ttl, pattern, palette = struct.unpack(_FMT, data)
    if magic != _MAGIC or version != _VERSION:
        return None
    if not 1 <= ttl <= TTL_INITIAL:        # 0 = spent; >initial = forged/clamped
        return None
    if pattern >= pattern_count or palette >= palette_count:
        return None
    return (origin, seq, ttl, pattern, palette)


# --- lifecycle --------------------------------------------------------------

def init(pattern_count: int, palette_count: int) -> None:
    """Bring the radio up on the pinned channel and reset all protocol state."""
    global _wlan, _espnow, _enabled, _mac, _counts, _seq
    global _last_broadcast_ms, _mute_until_ms, _dedup, _origin_last, _burst
    global _last_gc_ms
    import network                        # MicroPython-only; deferred for host tests
    import espnow

    _counts = (pattern_count, palette_count)
    _seq = 0
    _last_broadcast_ms = None
    _mute_until_ms = None
    _dedup = {}
    _origin_last = {}
    _burst = None
    _last_gc_ms = None

    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)
    _wlan.disconnect()                    # no AP: stop background reconnects
    _wlan.config(channel=CHANNEL)         # rendezvous channel for all badges
    _mac = _wlan.config("mac")
    _espnow = espnow.ESPNow()
    _espnow.active(True)
    _espnow.add_peer(_BCAST)
    _enabled = True


def opt_out() -> None:
    """User held Down 5s: radio hard off, ignore wireless until power cycle."""
    global _enabled, _burst
    _enabled = False
    _burst = None
    if _espnow is not None:
        _espnow.active(False)
    if _wlan is not None:
        _wlan.active(False)


def is_enabled() -> bool:
    return _enabled


def notify_user_activity(t_ms: int) -> None:
    """Any local button press: ignore incoming infections for a grace period
    so a user browsing patterns isn't overwritten mid-selection."""
    global _mute_until_ms
    _mute_until_ms = t_ms + INTERACTION_MUTE_MS


# --- sending ----------------------------------------------------------------

def broadcast(pattern: int, palette: int, t_ms: int) -> bool:
    """User tap: burst our current look with a fresh press id.

    Returns False (silently ignored) when disabled or within the local
    6s cooldown. A user tap replaces any relay burst in progress.
    """
    global _seq, _last_broadcast_ms, _burst
    if not _enabled:
        return False
    if _last_broadcast_ms is not None and \
            utime.ticks_diff(t_ms, _last_broadcast_ms) < COOLDOWN_MS:
        return False
    _last_broadcast_ms = t_ms
    _seq = (_seq + 1) & 0xFFFF
    _start_burst(pack(_mac, _seq, TTL_INITIAL, pattern, palette), t_ms)
    return True


def _start_burst(payload: bytes, start_ms: int) -> None:
    global _burst
    _burst = {"payload": payload, "next_ms": start_ms, "remaining": BURST_REPEATS}


# --- per-tick service -------------------------------------------------------

def service(t_ms: int):
    """Run the radio scheduler for this tick; drain and process any received
    packets. Returns (pattern, palette) if this badge was newly infected,
    else None. Call every main-loop iteration.
    """
    global _burst, _last_gc_ms
    if not _enabled:
        return None

    # The radio stays up continuously (duty-cycling wlan.active() at 1Hz froze
    # badges overnight — see module header), so just drain whatever arrived.
    infected = _drain(t_ms)

    # Emit any burst packets that have come due.
    while _burst is not None and utime.ticks_diff(t_ms, _burst["next_ms"]) >= 0:
        _espnow.send(_BCAST, _burst["payload"], False)
        _burst["remaining"] -= 1
        if _burst["remaining"] <= 0:
            _burst = None
        else:
            _burst["next_ms"] += BURST_SPACING_MS

    # Heap hygiene: long uptimes + per-tick allocations fragment MicroPython's
    # heap; a periodic collect keeps it compacted.
    if _last_gc_ms is None or utime.ticks_diff(t_ms, _last_gc_ms) >= LISTEN_PERIOD_MS:
        _last_gc_ms = t_ms
        gc.collect()

    return infected


def _drain(t_ms: int):
    """Process all queued packets; return the last accepted (pattern, palette)."""
    infected = None
    while _espnow.any():
        _sender, payload = _espnow.recv(0)
        fields = unpack(payload, _counts[0], _counts[1])
        if fields is None:
            continue
        origin, seq, ttl, pattern, palette = fields
        if origin == _mac:
            continue                      # our own burst echoed back
        if _mute_until_ms is not None and \
                utime.ticks_diff(_mute_until_ms, t_ms) > 0:
            continue                      # user is interacting: drop, don't dedup
        key = (origin, seq)
        if key in _dedup and utime.ticks_diff(_dedup[key], t_ms) > 0:
            continue                      # this press already passed through us
        last = _origin_last.get(origin)
        if last is not None and utime.ticks_diff(t_ms, last) < COOLDOWN_MS:
            continue                      # that badge is pressing too often
        # Accept: remember the press, adopt the look, maybe relay.
        _purge_dedup(t_ms)
        _dedup[key] = t_ms + DEDUP_TTL_MS
        _origin_last[origin] = t_ms
        infected = (pattern, palette)
        if ttl > 1 and _burst is None:    # single burst slot; drops are fine
            jitter = random.randrange(RELAY_JITTER_MAX_MS + 1)
            _start_burst(pack(origin, seq, ttl - 1, pattern, palette),
                         t_ms + jitter)
    return infected


def _purge_dedup(t_ms: int) -> None:
    expired = [k for k, exp in _dedup.items() if utime.ticks_diff(exp, t_ms) <= 0]
    for k in expired:
        del _dedup[k]
