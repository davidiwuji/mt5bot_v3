"""
STRATEGY: ema_rsi_pullback (suggested second strategy)

Why this one alongside session_range_breakout: your range strategy
trades a fixed time window once a day. This one is condition-based —
it only fires when trend AND momentum genuinely line up, so it
naturally sits out most of the day and trades less often but with a
clearer edge. Good complement if you want the bot active outside the
7:30am-6pm window too, without just adding more noise trades.

Logic:
  - TREND FILTER: price above EMA200 = uptrend bias, below = downtrend.
  - ENTRY: in an uptrend, wait for RSI(14) to dip to/below
    RSI_OVERSOLD then close back above it (a dip that's turning back
    up) -> BUY. In a downtrend, wait for RSI to rise to/above
    RSI_OVERBOUGHT then close back below it -> SELL.
  - SL: placed just beyond the recent swing low/high (last
    SWING_LOOKBACK candles).
  - TP: REWARD_RISK_RATIO times the SL distance.
"""

import pandas as pd
import numpy as np

from mt5bot.strategies import Signal

# --- strategy-specific settings (only affect this strategy) ---
EMA_PERIOD = 200
RSI_PERIOD = 14
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65
SWING_LOOKBACK = 10             # candles to look back for SL placement
REWARD_RISK_RATIO = 2.0


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def generate_signal(df: pd.DataFrame) -> Signal:
    if len(df) < EMA_PERIOD + SWING_LOOKBACK + 5:
        return Signal("none")

    df = df.copy()
    df["ema"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    df["rsi"] = _rsi(df["close"], RSI_PERIOD)

    prev = df.iloc[-2]
    last = df.iloc[-1]

    uptrend = last["close"] > last["ema"]
    downtrend = last["close"] < last["ema"]

    swing_low = df["low"].iloc[-SWING_LOOKBACK:].min()
    swing_high = df["high"].iloc[-SWING_LOOKBACK:].max()

    # Buy: uptrend + RSI was oversold and just crossed back above it
    if uptrend and prev["rsi"] <= RSI_OVERSOLD and last["rsi"] > RSI_OVERSOLD:
        sl = swing_low
        risk = last["close"] - sl
        if risk <= 0:
            return Signal("none")
        tp = last["close"] + risk * REWARD_RISK_RATIO
        return Signal("buy", sl=sl, tp=tp)

    # Sell: downtrend + RSI was overbought and just crossed back below it
    if downtrend and prev["rsi"] >= RSI_OVERBOUGHT and last["rsi"] < RSI_OVERBOUGHT:
        sl = swing_high
        risk = sl - last["close"]
        if risk <= 0:
            return Signal("none")
        tp = last["close"] - risk * REWARD_RISK_RATIO
        return Signal("sell", sl=sl, tp=tp)

    return Signal("none")
