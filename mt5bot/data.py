"""
DATA — pulls candle data from MT5 into a pandas DataFrame.

You shouldn't need to edit this file. Strategies call get_data() to
get their price history; this is just the plumbing that fetches it.
"""

import logging
import pandas as pd
import MetaTrader5 as mt5

from . import config

log = logging.getLogger("mt5_bot")


def get_data(n_candles: int = 500) -> pd.DataFrame:
    """
    Pull the last n_candles of OHLC data for the configured symbol
    and timeframe. Returns a DataFrame indexed by time (broker/server
    time, not Lagos time), with columns: open, high, low, close,
    tick_volume, spread, real_volume.

    500 candles on M15 covers several days of history, which is
    enough for session-window strategies (e.g. today's midnight-7:30am
    range) as well as trend/indicator strategies with longer lookbacks
    (e.g. a 200-period EMA).

    Returns an empty DataFrame if the pull fails (e.g. terminal not
    connected, symbol unavailable).
    """
    rates = mt5.copy_rates_from_pos(config.SYMBOL, config.TIMEFRAME, 0, n_candles)

    if rates is None or len(rates) == 0:
        log.error(f"No data returned for {config.SYMBOL}: {mt5.last_error()}")
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df
