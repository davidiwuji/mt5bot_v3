# Strategies

Three available out of the box:

| File | What it does |
|---|---|
| `ma_crossover.py` | Simple 20/50 moving average crossover — minimal example |
| `session_range_breakout.py` | Your strategy: 12:00am-7:30am Lagos high/low, trade the breakout, closes all trades by 6:00pm |
| `ema_rsi_pullback.py` | Trend (EMA200) + RSI pullback — fewer, higher-quality entries, no time restriction |
| `gold_scalper.py` | High-frequency mean-reversion scalp (Bollinger Bands + RSI + ATR stop). Needs `TIMEFRAME` set to M1/M5 and `CHECK_INTERVAL_SECONDS` lowered in `config.py` — see the notes at the top of the file before switching to it. |
| `hf_scalper.py` | Same idea as gold_scalper, but the target is a % of your current balance (grows automatically as the account grows) instead of a fixed band target. Pair with `MAX_TRADES_PER_DAY = None`. |
| `ny_session_breakout.py` | NY-session opening-range straddle using pending stop orders (buy-stop above / sell-stop below a small opening range). `MANAGES_OWN_ORDERS = True` — doesn't use the `generate_signal` interface below, see notes at the top of that file, including the daylight-saving calibration it needs twice a year. |
| `ema_vwap_atr.py` | EMA(9/21) momentum crossover confirmed by a VWAP trend filter, ATR-based stop, fixed 2:1 reward:risk. Scale-independent — works unchanged across symbols with very different price scales. Set `config.RISK_PERCENT = 2.0` to match its 2% risk rule. |

Set which one runs in `mt5bot/config.py`:
```python
ACTIVE_STRATEGY = "session_range_breakout"
```

## Adding your own

1. Copy any existing strategy file and rename it, e.g. `my_strategy.py`.
2. Write your logic inside `generate_signal(df)`. It must return a `Signal`:
   ```python
   from mt5bot.strategies import Signal

   def generate_signal(df):
       ...
       return Signal("buy", sl=1234.5, tp=1250.0)   # explicit SL/TP prices
       # or
       return Signal("sell")                          # falls back to config.py's SL_POINTS/TP_POINTS
       # or
       return Signal("none")                           # no trade this check
   ```
3. Optional: if your strategy shouldn't hold positions overnight or
   past a certain time, define this at module level (Lagos time,
   24-hour):
   ```python
   CLOSE_ALL_BY_LAGOS_HOUR = 18   # force-closes all this bot's trades at 6pm daily
   ```
4. Point `ACTIVE_STRATEGY` in `config.py` at your new file's name.

## Strategies that manage their own orders

A `generate_signal(df) -> Signal` strategy can only place ONE market
order per check. If a strategy needs something more involved — placing
two pending orders at once (a straddle), cancelling one once the other
fills, its own multi-day state — give it:
```python
MANAGES_OWN_ORDERS = True

def on_tick(df):
    ...   # do everything yourself, using mt5bot.trader's functions
```
`run.py` calls `on_tick(df)` directly instead of the normal
`generate_signal` → `place_trade` flow. See `ny_session_breakout.py`
for a full example (pending orders via `trader.place_pending_order()`,
`trader.cancel_all_pending_orders()`).

Keep strategy-specific numbers (RSI thresholds, range windows, reward:risk
ratio, etc.) as constants at the top of the strategy file itself — they
only affect that one strategy. Bot-wide settings (risk %, breakeven,
symbol, trade cap) stay in `config.py`.
