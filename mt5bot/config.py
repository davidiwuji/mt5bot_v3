"""
CONFIG — this is the file you'll actually edit day to day.

Everything here is a value/setting, not logic. If you want to change
risk, symbol, timeframe, trade limits, breakeven behavior, or which
strategy is active, change it here. Nothing else in the bot needs to
be touched for that.
"""

import MetaTrader5 as mt5

# ------------------------------------------------------------------
# MARKET
# ------------------------------------------------------------------

# Must match the EXACT symbol name shown in your MT5 Market Watch.
# Some brokers use suffixes/prefixes, e.g. "XAUUSD.", "GOLD", "XAUUSDm".
SYMBOL = "XAUUSD"

# Candle timeframe used to build the data your strategy analyzes.
# Common options: mt5.TIMEFRAME_M5, M15, M30, H1, H4, D1
TIMEFRAME = mt5.TIMEFRAME_M15

# ------------------------------------------------------------------
# STRATEGY SELECTION
# ------------------------------------------------------------------

# Name of the strategy module (file) inside mt5bot/strategies/ to use.
# Must match the filename without ".py".
#
# Available out of the box:
#   "ma_crossover"            -> simple example strategy (20/50 MA cross)
#   "session_range_breakout"  -> your 12am-7:30am Lagos high/low breakout
#   "ema_rsi_pullback"        -> trend + RSI pullback, fewer/higher-quality entries
#   "gold_scalper"            -> HF mean-reversion scalp (see notes in that file
#                                 before using — needs TIMEFRAME/CHECK_INTERVAL
#                                 tuned differently than the others)
#   "hf_scalper"              -> like gold_scalper, but the target is a % of
#                                 your current balance (e.g. ~$0.50 on $100)
#                                 instead of a fixed band/RR target, so it
#                                 grows automatically as the account grows.
#                                 Pair with MAX_TRADES_PER_DAY = None below.
#
# See mt5bot/strategies/README.md for how to add your own.
ACTIVE_STRATEGY = "session_range_breakout"

# ------------------------------------------------------------------
# RISK / TRADE SIZING
# ------------------------------------------------------------------

RISK_PERCENT = 1.0     # % of account balance risked per trade

# Used ONLY as a fallback for strategies that don't calculate their own
# SL/TP (e.g. ma_crossover). Strategies like session_range_breakout and
# ema_rsi_pullback calculate their own SL/TP based on market structure
# and ignore these two.
SL_POINTS = 300
TP_POINTS = 600

# ------------------------------------------------------------------
# BREAKEVEN ("set and forget, but move SL to BE once reasonably ahead")
# ------------------------------------------------------------------

BREAK_EVEN_ENABLED = True
# True  = Yes, once a trade is far enough in profit, move its SL to
#         the entry price (breakeven) so it can no longer lose money.
# False = No, leave the SL exactly where the strategy set it until
#         SL/TP is hit.

# How far in profit (as a multiple of the original SL distance) before
# the SL is moved to breakeven. 1.0 = once profit equals the amount
# originally risked. Only used if BREAK_EVEN_ENABLED is True.
BREAK_EVEN_TRIGGER_RR = 1.0

# ------------------------------------------------------------------
# TRADE FREQUENCY / BEHAVIOR
# ------------------------------------------------------------------

MAX_TRADES_PER_DAY = 3          # hard cap on new trades opened per day.
                                 # Set to None for NO cap — it still only ever holds
                                 # one position at a time, so "no cap" means it just
                                 # takes the next setup as soon as the last trade
                                 # closes, rather than stopping after N trades.

# How often (seconds) the bot checks for a brand-new entry signal.
CHECK_INTERVAL_SECONDS = 60

# How often (seconds) the bot refreshes the dashboard, checks
# breakeven conditions, and checks for a daily forced close-out. Kept
# short so the terminal display and BE moves feel responsive.
POSITION_CHECK_INTERVAL_SECONDS = 5

# Unique ID tagging every trade this bot places. Keeps it fully separate
# from any MQL5 EA or other bot running on the same account — do not
# reuse this number elsewhere.
MAGIC_NUMBER = 987654

# ------------------------------------------------------------------
# TIME / TIMEZONE
# ------------------------------------------------------------------

# MT5 candle timestamps come in your BROKER's server time, which is
# usually NOT the same as Lagos time (UTC+1, no daylight saving).
# Compare your MT5 terminal's clock (bottom-right of the platform, or
# the time on the price chart) against actual Lagos time, and set the
# number of hours to ADD to broker time to get Lagos time. E.g. if
# your broker's server clock reads 2:00am when it's midnight in Lagos,
# set this to -2. If it reads 10:00pm when it's midnight in Lagos, set
# this to +2. Get this right or time-based strategies will use the
# wrong window.
BROKER_TO_LAGOS_OFFSET_HOURS = 8

# ------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------

LOG_FILE = "mt5_bot.log"
