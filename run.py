"""
RUN — entry point. Start the bot with: python run.py

Opens a live dashboard right in this terminal window showing your
account balance/equity, open positions, and a running feed of events
(signal fired, trade opened, closed with P/L, moved to breakeven,
daily close-out). Detailed logs also go to mt5_bot.log in the
background.

You shouldn't need to edit this file. Behavior tweaks belong in
mt5bot/config.py; trading logic belongs in mt5bot/strategies/.
"""

import time
import logging

import MetaTrader5 as mt5

from mt5bot import config
from mt5bot.connection import connect, disconnect
from mt5bot.data import get_data
from mt5bot.trader import (
    place_trade,
    trades_opened_today,
    has_open_position,
    close_all_positions,
    check_and_apply_breakeven,
    get_open_positions_info,
    get_position_close_info,
)
from mt5bot.strategies import load_strategy
from mt5bot.timeutils import now_lagos
from mt5bot.dashboard import Dashboard

# File logging keeps running in the background even though the
# terminal itself is taken over by the live dashboard.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(config.LOG_FILE)],
)
log = logging.getLogger("mt5_bot")


def run():
    if not connect():
        print("Failed to connect to MT5. Check mt5_bot.log for details.")
        return

    strategy_module = load_strategy(config.ACTIVE_STRATEGY)
    generate_signal = strategy_module.generate_signal
    close_all_by_hour = getattr(strategy_module, "CLOSE_ALL_BY_LAGOS_HOUR", None)

    dash = Dashboard(strategy_name=config.ACTIVE_STRATEGY)
    dash.start()
    dash.log_event(f"Connected. Strategy '{config.ACTIVE_STRATEGY}' active.", style="bold green")
    log.info(f"Bot started. Active strategy: '{config.ACTIVE_STRATEGY}'.")

    last_signal_check = 0.0
    closed_out_on_date = None   # the Lagos date we last force-closed, so it only fires once/day
    previous_tickets = set()    # used to detect when a position disappears (SL/TP/close hit)

    try:
        while True:
            # --- refresh account + position display ---
            account = mt5.account_info()
            if account:
                dash.update_account(account.balance, account.equity)

            positions = get_open_positions_info()
            dash.update_positions(positions)

            # --- detect trades that closed since the last tick (SL/TP hit, etc.) ---
            current_tickets = {p["ticket"] for p in positions}
            for ticket in previous_tickets - current_tickets:
                info = get_position_close_info(ticket)
                if info:
                    style = "bold green" if info["profit"] >= 0 else "bold red"
                    dash.log_event(f"Position #{ticket} closed — P/L: {info['profit']:.2f}", style=style)
                else:
                    dash.log_event(f"Position #{ticket} closed.", style="white")
            previous_tickets = current_tickets

            # --- breakeven check (runs every tick, independent of new signals) ---
            moved = check_and_apply_breakeven()
            for ticket in moved:
                dash.log_event(f"Position #{ticket} moved to breakeven.", style="cyan")

            # --- forced daily close-out, if the active strategy defines one ---
            if close_all_by_hour is not None:
                lagos_now = now_lagos()
                today = lagos_now.date()
                if lagos_now.hour >= close_all_by_hour and closed_out_on_date != today:
                    closed = close_all_positions(reason="daily close-out")
                    if closed:
                        dash.log_event(
                            f"Daily close-out: closed {closed} position(s) at "
                            f"{close_all_by_hour}:00 Lagos time.",
                            style="yellow",
                        )
                    closed_out_on_date = today

            # --- new-signal check, throttled to CHECK_INTERVAL_SECONDS ---
            now_ts = time.time()
            if now_ts - last_signal_check >= config.CHECK_INTERVAL_SECONDS:
                last_signal_check = now_ts

                if trades_opened_today() >= config.MAX_TRADES_PER_DAY:
                    pass  # daily cap reached, stay quiet rather than spamming the feed
                elif has_open_position():
                    pass  # already in a trade from this bot, nothing new to check
                else:
                    df = get_data()
                    if not df.empty:
                        signal = generate_signal(df)
                        if signal.direction in ("buy", "sell"):
                            dash.log_event(
                                f"Signal: {signal.direction.upper()} "
                                f"(SL={signal.sl}, TP={signal.tp})",
                                style="bold magenta",
                            )
                            success = place_trade(signal.direction, sl=signal.sl, tp=signal.tp)
                            if success:
                                dash.log_event(
                                    f"Trade opened: {signal.direction.upper()} {config.SYMBOL}",
                                    style="bold green",
                                )
                            else:
                                dash.log_event("Trade failed to open — check mt5_bot.log", style="bold red")

            time.sleep(config.POSITION_CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        dash.log_event("Stopped manually.", style="yellow")
    finally:
        dash.stop()
        disconnect()


if __name__ == "__main__":
    run()
