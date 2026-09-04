"""
STRATEGY: session_range_breakout (fixed, now NTP-accurate)

Your strategy exactly as described:
  - RANGE: the high and low (wicks) of every candle between 00:00 and
    08:00 Lagos time, each day — this is your Asian-session range.
  - BUY: the first candle that FULLY CLOSES above the range high.
    SL = the range low.
  - SELL: the first candle that FULLY CLOSES below the range low.
    SL = the range high.
  - No fixed take-profit — the trade rides until it's stopped out, or
    force-closed at 6:00pm Lagos time (CLOSE_ALL_BY_LAGOS_HOUR below,
    read automatically by run.py). If you want a TP after all, see the
    note near REWARD_RISK_RATIO below.

WHAT WAS WRONG BEFORE (two separate issues, both fixed now):
  1. MT5's candle puller returns the CURRENTLY FORMING candle as the
     most recent row (its "close" is really just whatever price is
     right now, not a finished candle). The old version checked that
     still-forming row, so it could fire mid-candle on a wick spike —
     not an actual confirmed close. Fixed by checking the LAST FULLY
     CLOSED candle instead, and only on the FIRST candle that breaks
     the level (not every candle afterward that's still beyond it).
  2. now_lagos() was built from your PC's own system clock. If that
     clock has drifted or isn't synced, every time check here —
     "has the range finished forming yet", "is it still today" — shifts
     along with it, which would explain firing at the wrong time even
     with the confirmed-close fix in place. now_lagos() now corrects
     against a real NTP time server instead (see mt5bot/timeutils.py).

TWO SEPARATE CALIBRATIONS — BOTH MATTER, CHECK BOTH:
  - Your PC's clock accuracy: now fixed automatically via NTP.
  - Your BROKER's candle timestamps: still a manual setting
    (config.BROKER_TO_LAGOS_OFFSET_HOURS) — accurate real time doesn't
    help if this one is wrong, since the bot would be comparing
    correct current time against incorrectly-labeled candles. Check
    your MT5 terminal's clock against real Lagos time and set that
    value accordingly (see the comment above it in config.py). Get
    this wrong and the range window reads the wrong candles regardless
    of how accurate now_lagos() itself is — worth double-checking given
    how much this strategy depends on exact timing.
"""

from datetime import time as dtime

import pandas as pd

from mt5bot.strategies import Signal
from mt5bot.timeutils import to_lagos, now_lagos

# --- strategy-specific settings (only affect this strategy) ---
RANGE_START = dtime(0, 0)      # 00:00 Lagos
RANGE_END = dtime(8, 0)        # 08:00 Lagos — your Asian-session window

# Read automatically by run.py: force-close all of THIS bot's open
# trades at this Lagos hour, every day, no matter what.
CLOSE_ALL_BY_LAGOS_HOUR = 18   # 6:00pm

# Optional: if you'd rather take a fixed target than ride to the
# 6pm close-out, set this to a number (e.g. 2.0 for a 2:1 reward:risk
# target) and uncomment the two "tp = ..." lines below instead of the
# "tp=0.0" ones. Left as None / unused by default to match exactly
# what you described — no fixed TP.
REWARD_RISK_RATIO = None


def generate_signal(df: pd.DataFrame) -> Signal:
    # Need at least 2 fully closed candles (shift 1 and shift 2) plus
    # whatever candles make up the range window.
    if df.empty or len(df) < 3:
        return Signal("none")

    lagos_now = now_lagos()

    # Don't do anything until the range has fully formed.
    if lagos_now.time() < RANGE_END:
        return Signal("none")

    df = df.copy()
    df["lagos_time"] = to_lagos(df.index.to_series())
    df["lagos_date"] = df["lagos_time"].dt.date
    df["lagos_clock"] = df["lagos_time"].dt.time

    today = lagos_now.date()

    todays_range = df[
        (df["lagos_date"] == today)
        & (df["lagos_clock"] >= RANGE_START)
        & (df["lagos_clock"] < RANGE_END)
    ]

    if todays_range.empty:
        # No candles found for today's range window — likely a
        # data/time calibration issue, or not enough history pulled.
        return Signal("none")

    range_high = todays_range["high"].max()
    range_low = todays_range["low"].min()

    # Use the LAST FULLY CLOSED candle (shift 1), not the one still
    # forming (shift 0) — this is what makes "closes above the high"
    # an actual confirmed close. df.iloc[-1] is the forming candle,
    # df.iloc[-2] is the last one that actually finished.
    last_closed = df.iloc[-2]
    prior_closed = df.iloc[-3]

    last_close = last_closed["close"]
    prior_close = prior_closed["close"]

    # Only fire on the FIRST candle that breaks the level — if the
    # candle before it had already closed beyond the range too, this
    # isn't the breakout moment anymore, so stay out.
    first_break_up = last_close > range_high and prior_close <= range_high
    first_break_down = last_close < range_low and prior_close >= range_low

    if first_break_up:
        sl = range_low
        if REWARD_RISK_RATIO is not None:
            risk = last_close - sl
            tp = last_close + risk * REWARD_RISK_RATIO
            return Signal("buy", sl=sl, tp=tp)
        return Signal("buy", sl=sl, tp=0.0)  # 0.0 = no fixed take-profit

    if first_break_down:
        sl = range_high
        if REWARD_RISK_RATIO is not None:
            risk = sl - last_close
            tp = last_close - risk * REWARD_RISK_RATIO
            return Signal("sell", sl=sl, tp=tp)
        return Signal("sell", sl=sl, tp=0.0)

    return Signal("none")
