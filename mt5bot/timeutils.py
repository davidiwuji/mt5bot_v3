"""
TIMEUTILS — Lagos-time helpers for time-based strategies.

You shouldn't need to edit this file. Lagos runs on WAT (UTC+1) all
year with no daylight saving, so this is a fixed offset from UTC.

WHY THIS USES NTP INSTEAD OF THE SYSTEM CLOCK:
  now_lagos() used to be built from your PC's own clock
  (datetime.utcnow()). If that clock has drifted, isn't synced, or is
  just set wrong, every time-based check in a strategy — like
  session_range_breakout's midnight-8am window — shifts along with it
  silently. For a strategy where timing IS the strategy, that's a real
  problem. Now it queries a real NTP time server (the actual internet
  time protocol, the same thing your OS uses to sync its own clock)
  and corrects for any difference from your local clock.

  It does NOT hit the network on every call — that would slow down or
  risk breaking the bot's loop if your connection hiccups. It syncs
  once, caches the correction (the "offset"), and only re-queries every
  NTP_RESYNC_SECONDS. If a resync attempt fails (no internet, server
  down), it just keeps using the last known-good offset and logs a
  warning — it never crashes the bot over a network blip.

WHAT THIS DOES NOT FIX: your broker's candle timestamps are a SEPARATE
calibration (config.BROKER_TO_LAGOS_OFFSET_HOURS) — accurate real time
doesn't help if that offset is wrong, since the bot would then be
comparing correct current time against incorrectly-labeled candles.
Check both if a time-gated strategy still looks off.
"""

import time
import logging
from datetime import datetime, timedelta

import ntplib

from . import config

log = logging.getLogger("mt5_bot")

LAGOS_UTC_OFFSET_HOURS = 1  # fixed, Lagos does not observe DST

NTP_SERVERS = ["pool.ntp.org", "time.google.com", "time.cloudflare.com"]
NTP_RESYNC_SECONDS = 900    # resync every 15 minutes — frequent enough to catch
                             # drift, infrequent enough not to hammer NTP servers
                             # or slow down the bot's loop with network calls

_ntp_offset_seconds = 0.0      # correction applied to the local system clock
_last_sync_monotonic = None    # time.monotonic() timestamp of the last successful sync


def sync_now() -> bool:
    """
    Queries a real NTP time server and records the difference between
    it and this machine's system clock. Safe to call anytime (e.g. once
    at bot startup so you can see the correction in the log right
    away) — it's also called automatically and lazily by now_lagos()
    every NTP_RESYNC_SECONDS. Returns True if a server responded.
    """
    global _ntp_offset_seconds, _last_sync_monotonic
    client = ntplib.NTPClient()
    for server in NTP_SERVERS:
        try:
            response = client.request(server, version=3, timeout=3)
            _ntp_offset_seconds = response.offset
            _last_sync_monotonic = time.monotonic()
            log.info(f"NTP time synced via {server}. System clock offset: {_ntp_offset_seconds:+.3f}s")
            return True
        except Exception as e:
            log.warning(f"NTP sync via {server} failed: {e}")
    log.error(
        "Could not reach any NTP server. Falling back to the last known-good "
        "time correction (or the raw system clock, if this is the very first "
        "sync attempt) until the network is reachable again."
    )
    return False


def _corrected_utcnow() -> datetime:
    global _last_sync_monotonic
    needs_sync = (
        _last_sync_monotonic is None
        or (time.monotonic() - _last_sync_monotonic) >= NTP_RESYNC_SECONDS
    )
    if needs_sync:
        sync_now()  # updates the cached offset; on failure, keeps the old one

    return datetime.utcnow() + timedelta(seconds=_ntp_offset_seconds)


def now_lagos() -> datetime:
    """Current wall-clock time in Lagos, corrected against real NTP time."""
    return _corrected_utcnow() + timedelta(hours=LAGOS_UTC_OFFSET_HOURS)


def to_lagos(broker_time):
    """
    Convert a broker/server timestamp (or a pandas Series of them, as
    used for candle data) into Lagos time, using the calibration
    offset you set in config.BROKER_TO_LAGOS_OFFSET_HOURS. This is a
    SEPARATE calibration from the NTP correction above — it corrects
    for your BROKER's server clock, not your PC's.
    """
    return broker_time + timedelta(hours=config.BROKER_TO_LAGOS_OFFSET_HOURS)
