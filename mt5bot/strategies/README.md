# Strategies

Three available out of the box:

| File | What it does |
|---|---|
| `ma_crossover.py` | Simple 20/50 moving average crossover — minimal example |
| `session_range_breakout.py` | Your strategy: 12:00am-7:30am Lagos high/low, trade the breakout, closes all trades by 6:00pm |
| `ema_rsi_pullback.py` | Trend (EMA200) + RSI pullback — fewer, higher-quality entries, no time restriction |

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

Keep strategy-specific numbers (RSI thresholds, range windows, reward:risk
ratio, etc.) as constants at the top of the strategy file itself — they
only affect that one strategy. Bot-wide settings (risk %, breakeven,
symbol, trade cap) stay in `config.py`.
