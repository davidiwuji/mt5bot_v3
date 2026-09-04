"""
STRATEGY: ny_session_breakout (opening-range straddle breakout)

CONTEXT — please read before using this:
  This is built from the PUBLICLY documented mechanics of a category of
  paid "HFT Prop Firm EA" products (sold on MQL5, marketed on YouTube
  channels like the one you found). Those products are explicitly sold
  ONLY for passing prop-firm evaluation challenges with loose "HFT"
  rules — their own sellers state they are "not tested and not
  supported for live/real accounts" because real spread and slippage
  erase the edge. Their exact internal logic (an undisclosed "AI"
  detection system, a proprietary money-management scheme) is paid,
  closed-source IP I don't have access to and wouldn't reproduce even
  if I did.

  What this file implements instead is the well-known, generic public
  concept those products are built around: an OPENING RANGE BREAKOUT
  traded with pending stop orders at a session open. This is a
  legitimate, widely-documented technique on its own — not a copy of
  anyone's product — but it makes no promise of being profitable on a
  live account either. Demo-test thoroughly before considering it for
  anything else.

LOGIC:
  - At NY_SESSION_OPEN_LAGOS, the bot watches price for
    INITIAL_RANGE_MINUTES to build a small opening range (high/low).
  - It then places a BUY STOP just above that range's high and a SELL
    STOP just below its low — a "straddle." Whichever side price
    reaches first triggers the trade; the other pending order is
    cancelled immediately.
  - SL sits at the opposite side of the initial range (tight, since
    the range itself is small).
  - TP is a reward:risk multiple of the range size (REWARD_RISK_RATIO).
  - If neither side fills within TRADE_WINDOW_MINUTES, both pending
    orders are cancelled — no trade that day.
  - No trading on weekends. Only one attempt per calendar day.

THIS STRATEGY MANAGES ITS OWN ORDERS. Unlike the other strategies, it
doesn't return a Signal from generate_signal(df) — a straddle needs to
place TWO pending orders and cancel one once the other fills, which
doesn't fit that interface. Instead it defines on_tick(df), and
MANAGES_OWN_ORDERS = True tells run.py to call that directly.

SETUP NOTE — NY session open in Lagos time:
  US markets open 9:30am US Eastern. Eastern is UTC-5 (EST) most of the
  year, UTC-4 (EDT) roughly mid-March to early November. Lagos is fixed
  UTC+1. So NY open is:
    - EDT (roughly Mar-Nov): 9:30am ET = 2:30pm Lagos
    - EST (roughly Nov-Mar): 9:30am ET = 3:30pm Lagos
  NY_SESSION_OPEN_LAGOS below is set for EDT — flip it by an hour
  around the US DST changeover dates (mid-March, early November).
"""

from datetime import time as dtime
import logging

import pandas as pd
import MetaTrader5 as mt5

from mt5bot import config, trader
from mt5bot.timeutils import to_lagos, now_lagos

log = logging.getLogger("mt5_bot")

MANAGES_OWN_ORDERS = True   # tells run.py to call on_tick() instead of generate_signal()

# --- strategy-specific settings ---
NY_SESSION_OPEN_LAGOS = dtime(14, 30)   # 9:30am ET during EDT — see setup note above
INITIAL_RANGE_MINUTES = 5               # window used to build the opening range
TRADE_WINDOW_MINUTES = 30               # cancel unfilled orders after this long
BREAKOUT_BUFFER_POINTS = 20             # small buffer beyond the range high/low so
                                         # the order doesn't fill on noise right at the open
REWARD_RISK_RATIO = 1.5                 # TP = this many x the range size

# --- state, persists for the life of this run (resets once per day) ---
_state = {
    "date": None,
    "range_high": None,
    "range_low": None,
    "orders_placed": False,
    "done_for_today": False,
}


def _is_weekend(lagos_now) -> bool:
    return lagos_now.weekday() >= 5  # 5 = Saturday, 6 = Sunday


def on_tick(df: pd.DataFrame):
    lagos_now = now_lagos()
    today = lagos_now.date()

    if _is_weekend(lagos_now):
        return

    # Reset state at the start of a new day.
    if _state["date"] != today:
        _state.update(date=today, range_high=None, range_low=None,
                       orders_placed=False, done_for_today=False)

    if _state["done_for_today"]:
        return

    range_end = pd.Timestamp.combine(today, NY_SESSION_OPEN_LAGOS) + pd.Timedelta(minutes=INITIAL_RANGE_MINUTES)
    window_end = range_end + pd.Timedelta(minutes=TRADE_WINDOW_MINUTES)
    now_ts = pd.Timestamp.combine(today, lagos_now.time())
    session_open_ts = pd.Timestamp.combine(today, NY_SESSION_OPEN_LAGOS)

    # A straddle side already filled — cancel the other leg and stop
    # managing orders for today (breakeven/close-out is handled
    # generically by run.py for whatever position is now open).
    if trader.has_open_position():
        if _state["orders_placed"]:
            trader.cancel_all_pending_orders(reason="one side of the straddle filled")
            _state["orders_placed"] = False
        _state["done_for_today"] = True
        return

    # Not yet time to start watching the opening range.
    if now_ts < session_open_ts:
        return

    # Past the trade window with no fill at all — clean up, done for today.
    if now_ts > window_end:
        if _state["orders_placed"]:
            trader.cancel_all_pending_orders(reason="trade window expired, no fill")
            _state["orders_placed"] = False
        _state["done_for_today"] = True
        return

    # Still inside the opening-range window — nothing to do yet.
    if now_ts < range_end:
        return

    # Range window just finished and we haven't placed the straddle yet.
    if not _state["orders_placed"] and _state["range_high"] is None:
        df = df.copy()
        df["lagos_time"] = to_lagos(df.index.to_series())
        window_df = df[(df["lagos_time"] >= session_open_ts) & (df["lagos_time"] < range_end)]

        if window_df.empty:
            return  # no candles for the range window yet — try again next tick

        symbol_info = mt5.symbol_info(config.SYMBOL)
        if symbol_info is None:
            log.error("Could not get symbol info — skipping today's straddle.")
            _state["done_for_today"] = True
            return
        point = symbol_info.point

        range_high = window_df["high"].max()
        range_low = window_df["low"].min()
        range_size = range_high - range_low

        _state["range_high"] = range_high
        _state["range_low"] = range_low

        buy_entry = range_high + BREAKOUT_BUFFER_POINTS * point
        sell_entry = range_low - BREAKOUT_BUFFER_POINTS * point

        buy_tp = buy_entry + range_size * REWARD_RISK_RATIO
        sell_tp = sell_entry - range_size * REWARD_RISK_RATIO

        placed_buy = trader.place_pending_order("buy", buy_entry, sl=range_low, tp=buy_tp)
        placed_sell = trader.place_pending_order("sell", sell_entry, sl=range_high, tp=sell_tp)

        _state["orders_placed"] = placed_buy or placed_sell

        log.info(
            f"NY session straddle placed. Range=({range_low:.2f}, {range_high:.2f}) "
            f"buy@{buy_entry:.2f} sell@{sell_entry:.2f}"
        )
