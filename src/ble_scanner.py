# ble_scanner.py — BLE active scanner with SCAN_RSP capture
#
# Performs a BLE active scan. In active mode the stack sends SCAN_REQ packets
# to scannable advertisers, which reply with SCAN_RSP packets containing
# additional advertisement data (e.g. complete device name, extra UUIDs).
#
# adv_type values observed in _IRQ_SCAN_RESULT:
#   0x00  ADV_IND          connectable undirected advertisement
#   0x01  ADV_DIRECT_IND   connectable directed advertisement
#   0x02  ADV_NONCONN_IND  non-connectable undirected (no SCAN_RSP possible)
#   0x04  SCAN_RSP         scan response (only with active=True)
#   0x05  ADV_SCAN_IND     scannable undirected (triggers SCAN_RSP)
#
# IMPORTANT — memoryview aliasing:
#   The `addr` and `adv_data` objects passed into the IRQ handler are backed
#   by a reused internal buffer. You MUST copy them with bytes() immediately;
#   storing the raw memoryview will give corrupted data on the next event.
#
# IMPORTANT — gap_scan positional argument:
#   The `active` parameter is the 4th positional argument to gap_scan().
#   Pass it positionally (not as a keyword) for compatibility with
#   MicroPython versions prior to 1.20.

import bluetooth

_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE   = 6

ADV_TYPE_SCAN_RSP = 0x04

_ble         = None
_scan_rsp_cb = None   # optional callable(addr_type, addr, rssi, adv_data)
_results     = []     # accumulator used when no callback is set


# ---------------------------------------------------------------------------
# Internal IRQ handler
# ---------------------------------------------------------------------------

def _irq_handler(event, data):
    """
    BLE IRQ handler. Runs in MicroPython task context (soft IRQ) — heap
    allocation (bytes(), list.append, dict) is safe here.
    """
    if event == _IRQ_SCAN_RESULT:
        addr_type, addr, adv_type, rssi, adv_data = data

        if adv_type != ADV_TYPE_SCAN_RSP:
            return  # only interested in scan responses

        # Copy out of the reused internal buffers immediately.
        addr_bytes = bytes(addr)
        payload    = bytes(adv_data)

        if _scan_rsp_cb:
            _scan_rsp_cb(addr_type, addr_bytes, rssi, payload)
        else:
            _results.append({
                "addr_type": addr_type,
                "addr":      addr_bytes,
                "rssi":      rssi,
                "data":      payload,
            })

    elif event == _IRQ_SCAN_DONE:
        print("[ble_scanner] Scan complete.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init() -> None:
    """Power on the BLE radio and register the IRQ handler."""
    global _ble
    _ble = bluetooth.BLE()
    _ble.active(True)
    _ble.irq(_irq_handler)


def start_scan(
    duration_ms: int  = 0,
    interval_us: int  = 30_000,
    window_us: int    = 30_000,
    on_scan_rsp       = None,
) -> None:
    """
    Begin an active BLE scan.

    Args:
        duration_ms:  Total scan duration in ms. 0 = scan until stop_scan().
        interval_us:  Scan interval — how frequently to start a scan window.
        window_us:    Scan window — how long each interval actively listens.
                      Setting window == interval gives continuous scanning.
        on_scan_rsp:  Optional callback(addr_type, addr_bytes, rssi, adv_data).
                      If None, results are accumulated in get_results().

    Note: interval_us=30000, window_us=30000 is continuous scanning.
    For battery-sensitive applications use e.g. interval_us=100_000,
    window_us=10_000 (10% duty cycle).
    """
    global _scan_rsp_cb, _results
    _scan_rsp_cb = on_scan_rsp
    _results     = []
    # 4th argument True = active scan (positional, not keyword)
    _ble.gap_scan(duration_ms, interval_us, window_us, True)


def stop_scan() -> None:
    """Cancel an ongoing scan."""
    _ble.gap_scan(None)


def get_results() -> list:
    """
    Return a copy of accumulated SCAN_RSP records (when no callback was set).

    Each record is a dict with keys:
        addr_type (int), addr (bytes), rssi (int), data (bytes)
    """
    return list(_results)


def clear_results() -> None:
    """Discard accumulated results."""
    global _results
    _results = []


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def parse_ad_structures(adv_data: bytes) -> dict:
    """
    Parse BLE advertisement payload into a dict of {ad_type: payload_bytes}.

    Each AD structure in the payload has the format:
        [length (1B)] [type (1B)] [payload (length-1 bytes)]

    Common AD types:
        0x01  Flags
        0x02  Incomplete 16-bit UUIDs
        0x03  Complete 16-bit UUIDs
        0x08  Shortened Local Name
        0x09  Complete Local Name
        0xFF  Manufacturer Specific Data

    Example:
        ad = parse_ad_structures(payload)
        name = ad.get(0x09, b'').decode('utf-8', 'ignore')
    """
    ad = {}
    i  = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0:
            break
        if i + length >= len(adv_data):
            break  # malformed — truncated
        ad_type    = adv_data[i + 1]
        ad_payload = adv_data[i + 2 : i + 1 + length]
        ad[ad_type] = ad_payload
        i += 1 + length
    return ad


def format_addr(addr: bytes) -> str:
    """Format a 6-byte BLE address as 'XX:XX:XX:XX:XX:XX'."""
    return ":".join(f"{b:02X}" for b in addr)
