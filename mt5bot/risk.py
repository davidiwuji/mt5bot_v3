"""
RISK — position sizing math.

You shouldn't need to edit this file for normal use — it just converts
your RISK_PERCENT setting (from config.py) into an actual lot size
based on your live account balance and how many points are being
risked on a given trade. If you want to change HOW MUCH you risk
overall, change RISK_PERCENT in config.py instead of editing this.
"""

import logging
import MetaTrader5 as mt5

from . import config

log = logging.getLogger("mt5_bot")


def calculate_lot_size(sl_distance_points: float) -> float:
    """
    Work out a position size such that, if price moves sl_distance_points
    against the trade, the loss is approximately RISK_PERCENT of the
    current account balance.

    sl_distance_points is in POINTS (not price), so callers with an
    explicit SL price should convert it first: (entry_price - sl_price)
    / symbol point size.

    Falls back to the broker's minimum lot size if anything can't be
    calculated (e.g. missing symbol info).
    """
    account_info = mt5.account_info()
    symbol_info = mt5.symbol_info(config.SYMBOL)

    if account_info is None or symbol_info is None:
        return symbol_info.volume_min if symbol_info else 0.01

    balance = account_info.balance
    risk_amount = balance * (config.RISK_PERCENT / 100)

    point = symbol_info.point
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size

    sl_distance_price = sl_distance_points * point
    value_per_lot = (sl_distance_price / tick_size) * tick_value if tick_size else 0

    if value_per_lot <= 0:
        return symbol_info.volume_min

    lot = risk_amount / value_per_lot

    # Clamp to broker's allowed min/max, and round to the allowed step
    lot = max(symbol_info.volume_min, min(lot, symbol_info.volume_max))
    step = symbol_info.volume_step
    lot = round(lot / step) * step

    return round(lot, 2)
