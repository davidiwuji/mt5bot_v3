"""
STRATEGY: gold_scalper (high-frequency mean-reversion scalp, v2)

HONESTY NOTE FIRST: there is no strategy — this one included — that can
guarantee profitability or a "high win rate." What changed from v1
below are structural fixes to known weak points of mean-reversion
scalping, not a promise of better results. Backtest and demo this for
a good while before trusting it with real money.

WHAT CHANGED FROM v1 AND WHY:
  1. TREND FILTER — v1 faded every band touch, including during a
     strong trend. Fading a strong move is the single most common way
     mean-reversion scalpers lose. Now it skips buy-the-dip during a
     clear downtrend, and skips sell-the-rally during a clear uptrend.
  2. REVERSAL CONFIRMATION — instead of entering the instant price
     touches the band, it now waits for the candle to actually close
     back inside the band before entering. Cuts entries into a move
     that's still accelerating outward.
  3. VOLATILITY FLOOR — skips trades when ATR is too small relative to
     price, since a tiny scalp target barely covers spread/costs in a
     dead market.
  4. EXTENDED TARGET — target is the mean plus a small buffer instead
     of exactly the mean, since price commonly overshoots the average
     rather than stopping dead on it.

Logic (mean-reversion scalp):
  - Bollinger Bands (BB_PERIOD, BB_STD) define "stretched" price.
  - RSI(RSI_PERIOD) confirms momentum has gotten extreme, not just price.
  - EMA(TREND_EMA_PERIOD) defines the broader trend direction/filter.
  - BUY  when: price closed below the lower band last candle, closes
    back above it THIS candle (confirmed reversal), RSI was oversold,
    and the broader trend isn't strongly down.
  - SELL: the mirror image at the upper band.
  - TARGET: middle band + a small buffer in the trade's direction.
  - STOP: ATR-based, placed beyond the entry.
  - SPREAD FILTER: skips the trade if current spread is too wide.
  - VOLATILITY FLOOR: skips the trade if ATR is too small relative to
    price (market too quiet for the edge to cover costs).
  - SESSION FILTER: only trades during SESSION_START-SESSION_END
    (Lagos time).

SETUP NOTES (these live in config.py, not here — bot-wide settings):
  - TIMEFRAME: mt5.TIMEFRAME_M1 or M5 — built for fast candles.
  - CHECK_INTERVAL_SECONDS: lower this (e.g. 15-20).
  - MAX_TRADES_PER_DAY: raise this — start conservative, raise once
    you trust the results.
"""

from datetime import time as dtime

import pandas as pd
import numpy as np

from mt5bot.strategies import Signal
from mt5bot.timeutils import now_lagos

# --- strategy-specific settings (only affect this strategy) ---
BB_PERIOD = 20
BB_STD = 2.0
RSI_PERIOD = 7
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75

ATR_PERIOD = 14
SL_ATR_MULTIPLIER = 1.2        # stop = ATR * this, beyond entry

TP_BAND_BUFFER_MULTIPLIER = 0.15   # target = mean +/- (std * this), instead of exactly the mean

# Trend filter: EMA slope over TREND_LOOKBACK candles must not exceed
# TREND_SLOPE_THRESHOLD (in ATRs) against the trade direction, or the
# trade is skipped. Keeps the strategy from fighting a strong trend.
TREND_EMA_PERIOD = 50
TREND_LOOKBACK = 10
TREND_SLOPE_THRESHOLD = 0.8     # in units of current ATR

# Skip trades when the market's too quiet for the target to be worth it.
MIN_ATR_TO_PRICE_RATIO = 0.0003   # e.g. 0.03% — tune to your broker/instrument

MAX_SPREAD_POINTS = 300         # skip the trade if current spread exceeds this
                                 # (check your broker's typical XAUUSD spread)

SESSION_START = dtime(8, 0)     # 8:00am Lagos — roughly London open onward
SESSION_END = dtime(21, 0)      # 9:00pm Lagos — covers London + NY sessions


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(period).mean()


def generate_signal(df: pd.DataFrame) -> Signal:
    min_len = max(BB_PERIOD, ATR_PERIOD, TREND_EMA_PERIOD) + TREND_LOOKBACK + 5
    if len(df) < min_len:
        return Signal("none")

    # Session filter — only scalp during the active window.
    current_clock = now_lagos().time()
    if not (SESSION_START <= current_clock <= SESSION_END):
        return Signal("none")

    df = df.copy()
    df["ma"] = df["close"].rolling(BB_PERIOD).mean()
    df["std"] = df["close"].rolling(BB_PERIOD).std()
    df["upper"] = df["ma"] + BB_STD * df["std"]
    df["lower"] = df["ma"] - BB_STD * df["std"]
    df["rsi"] = _rsi(df["close"], RSI_PERIOD)
    df["atr"] = _atr(df, ATR_PERIOD)
    df["trend_ema"] = df["close"].ewm(span=TREND_EMA_PERIOD, adjust=False).mean()

    prev = df.iloc[-2]
    last = df.iloc[-1]

    if pd.isna(last["atr"]) or last["atr"] <= 0:
        return Signal("none")

    # Volatility floor — skip if the market's too quiet for the edge
    # to cover spread/costs.
    if (last["atr"] / last["close"]) < MIN_ATR_TO_PRICE_RATIO:
        return Signal("none")

    # Spread filter — "spread" comes straight from MT5's candle data.
    if "spread" in df.columns and last["spread"] > MAX_SPREAD_POINTS:
        return Signal("none")

    # Trend filter — how far the trend EMA has moved over the lookback,
    # measured in ATRs, tells us whether the market is trending hard.
    ema_now = df["trend_ema"].iloc[-1]
    ema_then = df["trend_ema"].iloc[-1 - TREND_LOOKBACK]
    trend_slope_in_atr = (ema_now - ema_then) / last["atr"]

    strong_downtrend = trend_slope_in_atr <= -TREND_SLOPE_THRESHOLD
    strong_uptrend = trend_slope_in_atr >= TREND_SLOPE_THRESHOLD

    # BUY: previous candle closed below the lower band (stretched),
    # this candle closes back above it (confirmed reversal), RSI
    # backs it up, and we're not fighting a strong downtrend.
    buy_setup = (
        prev["close"] <= prev["lower"]
        and last["close"] > last["lower"]
        and prev["rsi"] <= RSI_OVERSOLD
        and not strong_downtrend
    )
    if buy_setup:
        sl = last["close"] - last["atr"] * SL_ATR_MULTIPLIER
        tp = last["ma"] + last["std"] * TP_BAND_BUFFER_MULTIPLIER
        if tp <= last["close"] or sl >= last["close"]:
            return Signal("none")
        return Signal("buy", sl=sl, tp=tp)

    # SELL: mirror image at the upper band.
    sell_setup = (
        prev["close"] >= prev["upper"]
        and last["close"] < last["upper"]
        and prev["rsi"] >= RSI_OVERBOUGHT
        and not strong_uptrend
    )
    if sell_setup:
        sl = last["close"] + last["atr"] * SL_ATR_MULTIPLIER
        tp = last["ma"] - last["std"] * TP_BAND_BUFFER_MULTIPLIER
        if tp >= last["close"] or sl <= last["close"]:
            return Signal("none")
        return Signal("sell", sl=sl, tp=tp)

    return Signal("none")