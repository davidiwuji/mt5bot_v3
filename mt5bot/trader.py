"""
TRADER — sending orders, moving SL to breakeven, closing positions,
and checking trade/position status.

You shouldn't need to edit this file for normal use. This is the part
that actually talks to MT5 — the "how" of trading, not the "when"
(that's the strategy) or "how much" (that's risk.py / config.py).
"""

import logging
from datetime import datetime
import MetaTrader5 as mt5

from . import config
from .risk import calculate_lot_size

log = logging.getLogger("mt5_bot")


def place_trade(direction: str, sl: float = None, tp: float = None) -> bool:
    """
    Open a market order in the given direction ('buy' or 'sell') on
    the configured symbol.

    sl/tp are optional EXPLICIT PRICES (not points). Strategies that
    calculate their own stop/target based on market structure (like
    session_range_breakout) pass them in directly. If left as None,
    the fallback SL_POINTS/TP_POINTS from config.py are used instead.
    """
    symbol_info = mt5.symbol_info(config.SYMBOL)
    tick = mt5.symbol_info_tick(config.SYMBOL)
    if symbol_info is None or tick is None:
        log.error("Could not get symbol info/tick — aborting trade.")
        return False

    point = symbol_info.point

    if direction == "buy":
        price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY
        final_sl = sl if sl is not None else price - config.SL_POINTS * point
        final_tp = tp if tp is not None else price + config.TP_POINTS * point
    elif direction == "sell":
        price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
        final_sl = sl if sl is not None else price + config.SL_POINTS * point
        final_tp = tp if tp is not None else price - config.TP_POINTS * point
    else:
        log.error(f"Unknown trade direction: {direction}")
        return False

    # Convert the actual SL distance (in price) to points, so risk-based
    # lot sizing works the same whether SL came from config or a strategy.
    sl_distance_points = abs(price - final_sl) / point if point else config.SL_POINTS
    lot = calculate_lot_size(sl_distance_points)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": config.SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": final_sl,
        "tp": final_tp,
        "deviation": 20,
        "magic": config.MAGIC_NUMBER,
        "comment": "python-bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else mt5.last_error()
        comment = result.comment if result else ""
        log.error(f"Order failed: retcode={code}, comment={comment}")
        return False

    log.info(
        f"Trade placed: {direction.upper()} {lot} lots @ {price}, "
        f"SL={final_sl}, TP={final_tp}"
    )
    return True


def close_all_positions(reason: str = "") -> int:
    """
    Close every open position belonging to this bot (matched by
    MAGIC_NUMBER) on the configured symbol. Used for the daily forced
    close-out that some strategies define (e.g. session_range_breakout
    closing everything by 6pm Lagos time).

    Returns the number of positions successfully closed.
    """
    positions = mt5.positions_get(symbol=config.SYMBOL)
    if not positions:
        return 0

    tick = mt5.symbol_info_tick(config.SYMBOL)
    if tick is None:
        return 0

    closed = 0
    for pos in positions:
        if pos.magic != config.MAGIC_NUMBER:
            continue  # not this bot's trade (e.g. belongs to the MQL5 EA) — leave it alone

        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": config.SYMBOL,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 20,
            "magic": config.MAGIC_NUMBER,
            "comment": f"python-bot close ({reason})" if reason else "python-bot close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
            log.info(f"Closed position #{pos.ticket} ({reason})")
        else:
            code = result.retcode if result else mt5.last_error()
            log.error(f"Failed to close position #{pos.ticket}: {code}")

    return closed


def check_and_apply_breakeven() -> list:
    """
    If config.BREAK_EVEN_ENABLED is True, check every open position
    belonging to this bot and move its SL to entry price once it's
    ahead by BREAK_EVEN_TRIGGER_RR times the amount originally risked.

    Returns a list of ticket numbers that were just moved to breakeven
    this call (empty list if none, or if the feature is off).
    """
    moved = []

    if not config.BREAK_EVEN_ENABLED:
        return moved

    positions = mt5.positions_get(symbol=config.SYMBOL)
    if not positions:
        return moved

    tick = mt5.symbol_info_tick(config.SYMBOL)
    if tick is None:
        return moved

    for pos in positions:
        if pos.magic != config.MAGIC_NUMBER:
            continue

        if pos.sl == pos.price_open:
            continue  # already sitting at breakeven, nothing to do

        original_risk = abs(pos.price_open - pos.sl)
        if original_risk <= 0:
            continue  # no SL set on this position, can't measure risk

        if pos.type == mt5.POSITION_TYPE_BUY:
            current_profit_distance = tick.bid - pos.price_open
        else:
            current_profit_distance = pos.price_open - tick.ask

        trigger_distance = original_risk * config.BREAK_EVEN_TRIGGER_RR

        if current_profit_distance >= trigger_distance:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": config.SYMBOL,
                "position": pos.ticket,
                "sl": pos.price_open,
                "tp": pos.tp,
                "magic": config.MAGIC_NUMBER,
            }
            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                moved.append(pos.ticket)
                log.info(f"Position #{pos.ticket} moved to breakeven (SL={pos.price_open})")
            else:
                code = result.retcode if result else mt5.last_error()
                log.error(f"Failed to move #{pos.ticket} to breakeven: {code}")

    return moved


def trades_opened_today() -> int:
    """Count trades this bot (by magic number) has opened since midnight."""
    today_start = datetime.combine(datetime.now().date(), datetime.min.time())
    deals = mt5.history_deals_get(today_start, datetime.now())
    if deals is None:
        return 0
    return sum(
        1 for d in deals
        if d.magic == config.MAGIC_NUMBER and d.entry == mt5.DEAL_ENTRY_IN
    )


def has_open_position() -> bool:
    """True if this bot (by magic number) currently has an open position."""
    positions = mt5.positions_get(symbol=config.SYMBOL)
    if not positions:
        return False
    return any(p.magic == config.MAGIC_NUMBER for p in positions)


def get_open_positions_info() -> list:
    """
    Returns a plain-dict summary of this bot's open positions, used by
    the dashboard for display. Not used for trading decisions.
    """
    positions = mt5.positions_get(symbol=config.SYMBOL)
    if not positions:
        return []

    info = []
    for pos in positions:
        if pos.magic != config.MAGIC_NUMBER:
            continue
        info.append({
            "ticket": pos.ticket,
            "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
            "volume": pos.volume,
            "open_price": pos.price_open,
            "sl": pos.sl,
            "tp": pos.tp,
            "profit": pos.profit,
        })
    return info


def get_position_close_info(position_ticket: int):
    """
    After a position has closed, look up the closing deal for it in
    today's history and return {"profit": float, "price": float}.
    Returns None if not found (e.g. it closed on a previous day).
    Used by the dashboard to report P/L when a trade exits.
    """
    today_start = datetime.combine(datetime.now().date(), datetime.min.time())
    deals = mt5.history_deals_get(today_start, datetime.now())
    if not deals:
        return None
    for d in deals:
        if d.position_id == position_ticket and d.entry == mt5.DEAL_ENTRY_OUT:
            return {"profit": d.profit, "price": d.price}
    return None
