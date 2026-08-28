"""
TIMEUTILS — Lagos-time helpers for time-based strategies.

You shouldn't need to edit this file. Lagos runs on WAT (UTC+1) all
year with no daylight saving, so this is a fixed offset from UTC.
"""

from datetime import datetime, timedelta

from . import config

LAGOS_UTC_OFFSET_HOURS = 1  # fixed, Lagos does not observe DST


def now_lagos() -> datetime:
    """Current wall-clock time in Lagos, based on the system clock."""
    return datetime.utcnow() + timedelta(hours=LAGOS_UTC_OFFSET_HOURS)


def to_lagos(broker_time):
    """
    Convert a broker/server timestamp (or a pandas Series of them, as
    used for candle data) into Lagos time, using the calibration
    offset you set in config.BROKER_TO_LAGOS_OFFSET_HOURS.
    """
    return broker_time + timedelta(hours=config.BROKER_TO_LAGOS_OFFSET_HOURS)
