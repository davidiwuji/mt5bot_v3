"""
STRATEGIES package.

Each strategy lives in its own file in this folder and must expose a
generate_signal(df) function that returns a Signal (see below).

A strategy file can OPTIONALLY define:
    CLOSE_ALL_BY_LAGOS_HOUR = 18   # force-close all this bot's open
                                     positions at this hour, every day,
                                     regardless of SL/TP (e.g. for a
                                     session-based strategy that
                                     shouldn't hold overnight)

load_strategy() picks the active one based on config.ACTIVE_STRATEGY,
so the rest of the bot never needs to know which strategy is in use.
"""

import importlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    """
    What a strategy returns for each check.

    direction : "buy", "sell", or "none"
    sl        : explicit stop-loss PRICE. If None, the bot falls back
                to config.SL_POINTS from the current entry price.
    tp        : explicit take-profit PRICE. If None, the bot falls
                back to config.TP_POINTS from the current entry price.
    """
    direction: str
    sl: Optional[float] = None
    tp: Optional[float] = None


def load_strategy(name: str):
    """
    Import mt5bot/strategies/<name>.py and return the module itself,
    so the caller can access both generate_signal() and the optional
    CLOSE_ALL_BY_LAGOS_HOUR attribute.
    """
    module_path = f"mt5bot.strategies.{name}"
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            f"Strategy '{name}' not found. Expected a file at "
            f"mt5bot/strategies/{name}.py. Check config.ACTIVE_STRATEGY."
        ) from e

    if not hasattr(module, "generate_signal"):
        raise AttributeError(
            f"Strategy file '{name}.py' must define a generate_signal(df) function."
        )

    return module
