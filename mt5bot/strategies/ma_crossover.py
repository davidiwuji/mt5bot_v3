"""
STRATEGY: ma_crossover (simple example)

A basic 20/50 moving average crossover — kept as a minimal working
example. Doesn't calculate its own SL/TP, so it relies on the
SL_POINTS / TP_POINTS fallback values in config.py.

RULES FOR ANY STRATEGY FILE:
  - Must define generate_signal(df) -> Signal
  - df is a pandas DataFrame from mt5bot/data.py with columns:
    open, high, low, close, tick_volume, spread, real_volume
    (indexed by time, oldest row first, most recent row last)
  - Don't place trades or touch MT5 directly in here — just look at
    df and return a decision. The bot handles execution, risk,
    breakeven, and logging elsewhere.
"""

import pandas as pd

from mt5bot.strategies import Signal

# --- strategy-specific settings (only affect this strategy) ---
FAST_MA_PERIOD = 20
SLOW_MA_PERIOD = 50


def generate_signal(df: pd.DataFrame) -> Signal:
    """
    Buy when the fast MA crosses above the slow MA.
    Sell when the fast MA crosses below the slow MA.
    """
    if len(df) < SLOW_MA_PERIOD + 2:
        return Signal("none")

    df = df.copy()
    df["ma_fast"] = df["close"].rolling(FAST_MA_PERIOD).mean()
    df["ma_slow"] = df["close"].rolling(SLOW_MA_PERIOD).mean()

    prev = df.iloc[-2]
    last = df.iloc[-1]

    crossed_up = prev["ma_fast"] <= prev["ma_slow"] and last["ma_fast"] > last["ma_slow"]
    crossed_down = prev["ma_fast"] >= prev["ma_slow"] and last["ma_fast"] < last["ma_slow"]

    if crossed_up:
        return Signal("buy")
    elif crossed_down:
        return Signal("sell")
    return Signal("none")
