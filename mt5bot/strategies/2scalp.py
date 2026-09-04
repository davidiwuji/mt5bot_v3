"""
STRATEGY: ema_rsi_vwap

A trend-following and momentum strategy that generates buy and sell signals based on:
  - EMA Fast/Slow Crossovers (9/21 periods)
  - RSI momentum filtering (< 60 for long entries, > 75 for exits)
  - Volume-Weighted Average Price (VWAP) trend confirmation (price > VWAP for long entries)
  - Dynamic ATR-based Stop-Loss (1.5x ATR) and Take-Profit (1:2 Risk-to-Reward ratio)

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
FAST_EMA_PERIOD = 9
SLOW_EMA_PERIOD = 21
RSI_PERIOD = 14
ATR_PERIOD = 14
RSI_BUY_MAX = 60
RSI_SELL_MIN = 75
ATR_SL_MULTIPLIER = 1.5
REWARD_RISK_RATIO = 2.0


def _calculate_rsi(series: pd.Series, period: int) -> pd.Series:
    """Calculates Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def _calculate_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculates Average True Range (ATR)."""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def _calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculates Volume-Weighted Average Price (VWAP)."""
    volume = df["real_volume"] if "real_volume" in df.columns and df["real_volume"].sum() > 0 else df["tick_volume"]
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    tpv = typical_price * volume
    return tpv.cumsum() / volume.cumsum().replace(0, 1e-10)


def generate_signal(df: pd.DataFrame) -> Signal:
    """
    Buy when fast EMA crosses above slow EMA, RSI < 60, and price > VWAP.
    Sell when fast EMA crosses below slow EMA or RSI > 75.
    Calculates dynamic ATR-based SL and TP.
    """
    min_required_bars = max(SLOW_EMA_PERIOD, RSI_PERIOD, ATR_PERIOD) + 2
    if len(df) < min_required_bars:
        return Signal("none")

    df = df.copy()

    # Calculate indicators
    df["ema_fast"] = df["close"].ewm(span=FAST_EMA_PERIOD, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=SLOW_EMA_PERIOD, adjust=False).mean()
    df["rsi"] = _calculate_rsi(df["close"], RSI_PERIOD)
    df["atr"] = _calculate_atr(df, ATR_PERIOD)
    df["vwap"] = _calculate_vwap(df)

    prev = df.iloc[-2]
    last = df.iloc[-1]

    # Crossover logic
    ema_bullish_cross = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
    ema_bearish_cross = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]

    # Entry and Exit Signals
    crossed_up = ema_bullish_cross and (last["rsi"] < RSI_BUY_MAX) and (last["close"] > last["vwap"])
    crossed_down = ema_bearish_cross or (last["rsi"] > RSI_SELL_MIN)

    if crossed_up:
        entry_price = last["close"]
        atr_val = last["atr"]
        sl = entry_price - (atr_val * ATR_SL_MULTIPLIER)
        tp = entry_price + ((entry_price - sl) * REWARD_RISK_RATIO)
        return Signal("buy", sl=sl, tp=tp)

    elif crossed_down:
        entry_price = last["close"]
        atr_val = last["atr"]
        sl = entry_price + (atr_val * ATR_SL_MULTIPLIER)
        tp = entry_price - ((sl - entry_price) * REWARD_RISK_RATIO)
        return Signal("sell", sl=sl, tp=tp)

    return Signal("none")