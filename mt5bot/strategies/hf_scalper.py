"""
STRATEGY: hf_scalper (fast mean-reversion scalp, dollar-scaled target)

Same idea as gold_scalper, tuned for higher frequency and a target that
scales with your account instead of a band/RR-based one:
  - Timeframe: meant to be run with config.TIMEFRAME = mt5.TIMEFRAME_M1.
  - Target: TARGET_PROFIT_PERCENT_OF_BALANCE of your CURRENT balance,
    via Signal.tp_usd (the bot converts this into an actual price once
    it knows the trade's lot size — see mt5bot/trader.py). On a $100
    balance that's ~$0.50/trade by default; it grows automatically as
    your balance grows, no manual adjustment needed.
  - Risk: uses the normal config.RISK_PERCENT for the stop-loss side,
    same as every other strategy.
  - No daily trade cap by design — set config.MAX_TRADES_PER_DAY = None
    to match. It still only ever holds one position at a time.

HONESTY NOTE: same as gold_scalper — no strategy can promise it will be
profitable, or that gains stay small while losses stay small as a rule.
This keeps both proportional to your balance IF the underlying logic
has a real edge; only backtesting/demo trading over real time tells you
that.

Signal logic (identical filters to gold_scalper v2, tuned for M1):
  - Bollinger Bands define "stretched" price, RSI confirms the extreme.
  - Entry only on a CONFIRMED reversal (closed outside the band one
    candle, closes back inside the next).
  - EMA trend filter blocks fading a strong trend.
  - ATR-based stop, kept tight to match the small target.
  - Volatility floor + spread filter.
"""

import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from mt5bot.strategies import Signal

# --- strategy-specific settings (only affect this strategy) ---
BB_PERIOD = 20
BB_STD = 2.0
RSI_PERIOD = 7
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

ATR_PERIOD = 14
SL_ATR_MULTIPLIER = 1.0        # tight stop — keeps losses small, matching the small target

TREND_EMA_PERIOD = 50
TREND_LOOKBACK = 10
TREND_SLOPE_THRESHOLD = 0.8    # in units of ATR — blocks fading a strong trend

MIN_ATR_TO_PRICE_RATIO = 0.0002   # volatility floor — skip trades in a dead-quiet market
MAX_SPREAD_POINTS = 300

# --- dollar-scaled target settings ---
TARGET_PROFIT_PERCENT_OF_BALANCE = 0.5   # % of current balance targeted as profit per win
                                          # e.g. ~$0.50 on a $100 balance, ~$1.00 on $200, etc.
MIN_TARGET_USD = 0.10                    # floor so the target never gets silly-small


def _current_target_usd() -> float:
    """
    Converts TARGET_PROFIT_PERCENT_OF_BALANCE into an actual dollar
    figure using the CURRENT account balance — this is what makes the
    target grow automatically as the account grows. Needs to happen
    here (not in trader.py) because it's a strategy-specific setting.
    """
    account = mt5.account_info()
    if account is None:
        return MIN_TARGET_USD
    return max(MIN_TARGET_USD, account.balance * (TARGET_PROFIT_PERCENT_OF_BALANCE / 100))


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

    df = df.copy()
    df["ma"] = df["close"].rolling(BB_PERIOD).mean()
    df["std"] = df["close"].rolling(BB_PERIOD).std()
    df["upper"] = df["ma"] + BB_STD * df["std"]
    df["lower"] = df["ma"] - BB_STD * df["std"]
    df["rsi"] = _rsi(df["close"], RSI_PERIOD)
    df["atr"] = _atr(df, ATR_PERIOD)
    df["trend_ema"] = df["close"].ewm(span=TREND_EMA_PERIOD, adjust=False).mean()

    # Use the last two FULLY CLOSED candles (shift 1, shift 2), never the
    # still-forming one — df.iloc[-1] is forming, df.iloc[-2] is the last
    # confirmed close, df.iloc[-3] is the one before that.
    prev = df.iloc[-3]
    last = df.iloc[-2]

    if pd.isna(last["atr"]) or last["atr"] <= 0:
        return Signal("none")

    # Volatility floor.
    if (last["atr"] / last["close"]) < MIN_ATR_TO_PRICE_RATIO:
        return Signal("none")

    # Spread filter.
    if "spread" in df.columns and last["spread"] > MAX_SPREAD_POINTS:
        return Signal("none")

    # Trend filter — EMA slope over TREND_LOOKBACK candles, in ATRs.
    ema_now = df["trend_ema"].iloc[-2]
    ema_then = df["trend_ema"].iloc[-2 - TREND_LOOKBACK]
    trend_slope_in_atr = (ema_now - ema_then) / last["atr"]
    strong_downtrend = trend_slope_in_atr <= -TREND_SLOPE_THRESHOLD
    strong_uptrend = trend_slope_in_atr >= TREND_SLOPE_THRESHOLD

    # BUY: confirmed reversal off the lower band, trend not against us.
    if (prev["close"] <= prev["lower"] and last["close"] > last["lower"]
            and prev["rsi"] <= RSI_OVERSOLD and not strong_downtrend):
        sl = last["close"] - last["atr"] * SL_ATR_MULTIPLIER
        return Signal("buy", sl=sl, tp_usd=_current_target_usd())

    # SELL: mirror image at the upper band.
    if (prev["close"] >= prev["upper"] and last["close"] < last["upper"]
            and prev["rsi"] >= RSI_OVERBOUGHT and not strong_uptrend):
        sl = last["close"] + last["atr"] * SL_ATR_MULTIPLIER
        return Signal("sell", sl=sl, tp_usd=_current_target_usd())

    return Signal("none")
