"""
CONNECTION — handles attaching to the running MT5 terminal.

You shouldn't need to edit this file. It just opens/closes the link
between this Python script and your already-running, already-logged-in
MT5 terminal.
"""

import logging
import MetaTrader5 as mt5

from . import config

log = logging.getLogger("mt5_bot")


def connect() -> bool:
    """
    Attach to the running MT5 terminal (it must already be open and
    logged into your broker account — this does NOT log in for you).
    Returns True if connected successfully and the configured symbol
    is available, False otherwise.
    """
    if not mt5.initialize():
        log.error(f"initialize() failed, error code = {mt5.last_error()}")
        return False

    account_info = mt5.account_info()
    if account_info is None:
        log.error("Could not fetch account info — is MT5 open and logged in?")
        return False

    log.info(
        f"Connected. Account: {account_info.login}, "
        f"Balance: {account_info.balance}, "
        f"Server: {account_info.server}"
    )

    symbol_info = mt5.symbol_info(config.SYMBOL)
    if symbol_info is None:
        log.error(
            f"Symbol '{config.SYMBOL}' not found. Check the exact symbol "
            f"name in your MT5 Market Watch (broker suffixes vary) and "
            f"update SYMBOL in config.py."
        )
        return False

    if not symbol_info.visible:
        mt5.symbol_select(config.SYMBOL, True)

    return True


def disconnect():
    """Cleanly shut down the connection to the terminal."""
    mt5.shutdown()
