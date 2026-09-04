"""
STRATEGY: ema_vwap_atr

Built from this spec:

    Parameter            Type          Default   Purpose
    CAPITAL_RISK_PCT      Risk Rule     2%        Risk per trade
    REWARD_RISK_RATIO     Exit Rule     2.0       Target = 2x risk (1:2)
    FAST_EMA / SLOW_EMA   Indicator     9 / 21    Short-to-medium momentum shift
    ATR_PERIOD            Volatility    14        Adaptive stop-loss distance
    VWAP                  Trend Filter  —         Only trade with the institutional average

WORKS WITH ANY SYMBOL — what that means and what it doesn't:
  Every calculation here (EMA, ATR, VWAP) operates in the SAME units as
  price itself, so none of them care whether price is 2000 (gold), 1.10
  (EURUSD), or 42000 (an index) — they scale automatically. The one
  thing that would NOT have scaled is a spread filter written in fixed
  points, since a "300 point" spread means something completely
  different on gold vs EURUSD vs an index — it would silently block
  every trade on some symbols and do nothing on others. Fixed here by
  measuring spread as a fraction of ATR instead (MAX_SPREAD_TO_ATR_RATIO)
  — a relative measure that means the same thing on any instrument.

  What this does NOT do: trade multiple symbols at once. This bot's
  config.SYMBOL is a single global setting — point it at whichever
  instrument you want to run this on, and the logic works unchanged.
  Running several symbols simultaneously would need a bigger change to
  connection.py/data.py/trader.py (they're all built around one
  SYMBOL) — say if you want that and I'll build it separately.

  CAPITAL_RISK_PCT: this is already what config.RISK_PERCENT does in
  this framework (used by every strategy's lot sizing) — set
  config.RISK_PERCENT = 2.0 rather than duplicating it here, so risk
  sizing stays in one place across all your strategies.

Logic:
  - VWAP is calculated fresh each trading day (resets at midnight in
    whatever timezone your broker's candle timestamps use) — cumulative
    (typical price x volume) / cumulative volume, using MT5's
    tick_volume as the volume proxy (retail forex/CFDs don't have real
    traded volume).
  - BUY: fast EMA crosses above slow EMA AND price is above VWAP
    (momentum shift with the institutional trend, not against it).
  - SELL: mirror image — fast EMA crosses below slow EMA AND price is
    below VWAP.
  - SL: ATR x SL_ATR_MULTIPLIER beyond entry.
  - TP: REWARD_RISK_RATIO x the SL distance.
  - Uses the last two FULLY CLOSED candles (never the still-forming
    one) so the crossover is a confirmed close, not a live/intrabar
    price — same fix applied to every other strategy in this bot.
"""

import pandas as pd
import MetaTrader5 as mt5

from mt5bot import config
from mt5bot.strategies import Signal

# --- strategy-specific settings (only affect this strategy) ---
FAST_EMA_PERIOD = 9
SLOW_EMA_PERIOD = 21
ATR_PERIOD = 14
SL_ATR_MULTIPLIER = 1.5          # not specified in the spec — reasonable default, tune freely
REWARD_RISK_RATIO = 2.0

MAX_SPREAD_TO_ATR_RATIO = 0.15   # skip the trade if spread eats more than this fraction
                                  # of the stop distance — same meaning on any symbol


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(period).mean()


def _vwap(df: pd.DataFrame) -> pd.Series:
    """
    Session VWAP, resetting each calendar day (broker time). Uses
    tick_volume as the volume proxy, and typical price (H+L+C)/3 as the
    price input, which is the standard VWAP formula.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    volume = df["tick_volume"]

    day = df.index.normalize()  # midnight of each row's own day
    cum_pv = (typical_price * volume).groupby(day).cumsum()
    cum_vol = volume.groupby(day).cumsum()

    return cum_pv / cum_vol.replace(0, pd.NA)


def generate_signal(df: pd.DataFrame) -> Signal:
    min_len = max(SLOW_EMA_PERIOD, ATR_PERIOD) + 5
    if len(df) < min_len:
        return Signal("none")

    df = df.copy()
    df["fast_ema"] = df["close"].ewm(span=FAST_EMA_PERIOD, adjust=False).mean()
    df["slow_ema"] = df["close"].ewm(span=SLOW_EMA_PERIOD, adjust=False).mean()
    df["atr"] = _atr(df, ATR_PERIOD)
    df["vwap"] = _vwap(df)

    # Last two FULLY CLOSED candles — df.iloc[-1] is still forming,
    # df.iloc[-2] is the last confirmed close, df.iloc[-3] the one before.
    prev = df.iloc[-3]
    last = df.iloc[-2]

    if pd.isna(last["atr"]) or last["atr"] <= 0 or pd.isna(last["vwap"]):
        return Signal("none")

    # Spread filter, expressed relative to ATR so it means the same
    # thing regardless of the symbol's price scale. MT5's "spread"
    # column is in POINTS, ATR is in PRICE units — need the symbol's
    # point size to compare them, which a strategy doesn't get from df
    # alone, so we ask MT5 directly for it.
    if "spread" in df.columns:
        symbol_info = mt5.symbol_info(config.SYMBOL)
        if symbol_info is not None and symbol_info.point > 0:
            spread_in_price_units = last["spread"] * symbol_info.point
            if spread_in_price_units > last["atr"] * MAX_SPREAD_TO_ATR_RATIO:
                return Signal("none")

    # Momentum shift: fast EMA crossing the slow EMA.
    crossed_up = prev["fast_ema"] <= prev["slow_ema"] and last["fast_ema"] > last["slow_ema"]
    crossed_down = prev["fast_ema"] >= prev["slow_ema"] and last["fast_ema"] < last["slow_ema"]

    # BUY: bullish cross, confirmed by price trading above the
    # institutional average (VWAP).
    if crossed_up and last["close"] > last["vwap"]:
        sl = last["close"] - last["atr"] * SL_ATR_MULTIPLIER
        risk = last["close"] - sl
        if risk <= 0:
            return Signal("none")
        tp = last["close"] + risk * REWARD_RISK_RATIO
        return Signal("buy", sl=sl, tp=tp)

    # SELL: bearish cross, confirmed by price trading below VWAP.
    if crossed_down and last["close"] < last["vwap"]:
        sl = last["close"] + last["atr"] * SL_ATR_MULTIPLIER
        risk = sl - last["close"]
        if risk <= 0:
            return Signal("none")
        tp = last["close"] - risk * REWARD_RISK_RATIO
        return Signal("sell", sl=sl, tp=tp)

    return Signal("none")
