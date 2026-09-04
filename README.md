# XAUUSD MT5 Python Bot

## Folder layout

```
mt5bot_v3/
├── run.py                        ← start the bot: python run.py
├── start_bot.bat                 ← Windows: double-click to open the bot in its own console window
├── requirements.txt
├── mt5bot/
│   ├── config.py                  ← EDIT THIS for settings (symbol, risk, breakeven, active strategy, etc.)
│   ├── connection.py              ← connects to the MT5 terminal (don't need to touch)
│   ├── data.py                    ← pulls candle data (don't need to touch)
│   ├── risk.py                    ← lot size math from RISK_PERCENT (don't need to touch)
│   ├── trader.py                  ← sends orders, breakeven, close-out, position tracking (don't need to touch)
│   ├── dashboard.py                ← live terminal display (don't need to touch)
│   ├── timeutils.py                ← Lagos time helpers (don't need to touch)
│   └── strategies/
│       ├── ma_crossover.py          ← simple example strategy
│       ├── session_range_breakout.py ← your 12am-7:30am Lagos range breakout, closes by 6pm
│       ├── ema_rsi_pullback.py      ← trend + RSI pullback strategy
│       ├── gold_scalper.py          ← high-frequency mean-reversion scalp
│       └── README.md               ← how to add your own strategy
```

**Rule of thumb:** if you want to change a *number or on/off setting*
(risk %, breakeven, SL/TP fallback, symbol, timeframe, max trades/day,
active strategy) → edit `mt5bot/config.py`.
If you want to change your *trading logic* → edit or add a file in
`mt5bot/strategies/`.
Everything else you shouldn't need to open.

## 1. Requirements
- Windows machine (the `MetaTrader5` package is Windows-only)
- MT5 desktop terminal installed and **logged into your broker account**, kept running
- Python 3.10+

```
pip install -r requirements.txt
```

## 2. Before running
- In MT5 → Market Watch, confirm the exact symbol name for gold on
  your broker (e.g. `XAUUSD`, `XAUUSD.`, `GOLD`, `XAUUSDm`). Update
  `SYMBOL` in `mt5bot/config.py` if it doesn't match.
- In MT5 → Tools → Options → Expert Advisors, make sure **"Allow Algo
  Trading"** is checked, or order requests will be rejected.
- If you're using `session_range_breakout`, check your MT5 terminal's
  clock against real Lagos time and set
  `BROKER_TO_LAGOS_OFFSET_HOURS` in `config.py` accordingly (explained
  in the comment right above that setting).

## 3. Run it
```
python run.py
```
or on Windows, just double-click `start_bot.bat` to run it in its own
console window. Either way you'll see a live-updating dashboard: your
balance/equity, a table of open positions, and a running feed of
events (signals, trades opened, closed with P/L, moved to breakeven,
daily close-outs). Full detail also logs quietly to `mt5_bot.log`.

Press `Ctrl+C` to stop.

## 4. Strategies
Three ship with the bot — pick one in `config.py`'s `ACTIVE_STRATEGY`:

- `session_range_breakout` — your strategy: 12:00am-7:30am Lagos
  high/low range, buy on a breakout above the high (SL at the range
  low) or sell on a breakout below the low (SL at the range high), and
  force-closes everything by 6:00pm Lagos time.
- `ema_rsi_pullback` — trend (EMA200) + RSI pullback entries, no time
  restriction, fires less often but only on higher-quality setups.
- `ma_crossover` — simple 20/50 MA crossover, kept as a minimal example.
- `gold_scalper` — high-frequency mean-reversion scalp (Bollinger Bands +
  RSI + ATR-based stop, spread and session filters). Trades often with a
  small target, so most trades are small wins — but if price keeps
  trending instead of snapping back, a loss can outsize a typical win.
  Needs `TIMEFRAME` set to M1 or M5 and `CHECK_INTERVAL_SECONDS` lowered
  (e.g. 15-20s) in `config.py` — see the notes at the top of that
  strategy file before switching to it, and demo-trade it first.

See `mt5bot/strategies/README.md` for how to write your own.

## 5. Breakeven ("set and forget")
In `config.py`:
```python
BREAK_EVEN_ENABLED = True     # Yes/No — move SL to entry once a trade is far enough ahead
BREAK_EVEN_TRIGGER_RR = 1.0   # how far ahead (as a multiple of the amount risked) before it moves
```
With this on, once a trade is up by `BREAK_EVEN_TRIGGER_RR` × its
original risk, the bot moves its stop loss to the entry price so the
trade can no longer turn into a loss — checked every few seconds,
independent of when the strategy last looked for a new signal.

## 6. Safety notes
- Fully separate from any MQL5 EA — trades are tagged with
  `MAGIC_NUMBER` in `config.py` so this bot never touches or gets
  confused by trades from anything else running on the same account.
- Won't open a new trade while one of its own is already open, and
  respects `MAX_TRADES_PER_DAY`.
- Your target of 2+ trades/day at >65% win rate depends entirely on
  the strategy logic — the framework can run it unattended, cap
  frequency, and manage risk, but it can't guarantee a win rate.
  Backtest and demo-trade before going live.
