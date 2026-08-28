"""
DASHBOARD — live terminal display of what the bot is doing.

You shouldn't need to edit this file. It only renders what's already
happening (connection status, open positions, recent events) — it
doesn't make any trading decisions. Uses the 'rich' library to update
in place in the same terminal window you launched the bot from.
"""

from collections import deque
from datetime import datetime

from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.console import Group
from rich.text import Text

MAX_EVENTS = 12  # how many recent events stay visible on screen


class Dashboard:
    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        self.events = deque(maxlen=MAX_EVENTS)
        self.balance = None
        self.equity = None
        self._positions = []
        self._live = Live(self._render(), refresh_per_second=2, screen=False)

    def start(self):
        self._live.start()

    def stop(self):
        self._live.stop()

    def log_event(self, message: str, style: str = "white"):
        """Add a line to the scrolling event feed (newest on top)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.events.appendleft(Text(f"[{timestamp}] {message}", style=style))
        self._live.update(self._render())

    def update_account(self, balance: float, equity: float):
        self.balance = balance
        self.equity = equity
        self._live.update(self._render())

    def update_positions(self, positions: list):
        self._positions = positions
        self._live.update(self._render())

    def _render(self):
        balance_str = f"{self.balance:.2f}" if self.balance is not None else "—"
        equity_str = f"{self.equity:.2f}" if self.equity is not None else "—"

        header = Text(
            f"MT5 Bot  |  Strategy: {self.strategy_name}  |  "
            f"Balance: {balance_str}  |  Equity: {equity_str}",
            style="bold cyan",
        )

        pos_table = Table(title="Open Positions", expand=True)
        for col in ["Ticket", "Type", "Volume", "Open", "SL", "TP", "Profit"]:
            pos_table.add_column(col)

        if not self._positions:
            pos_table.add_row("—", "—", "—", "—", "—", "—", "—")
        else:
            for p in self._positions:
                profit_style = "green" if p["profit"] >= 0 else "red"
                pos_table.add_row(
                    str(p["ticket"]),
                    p["type"],
                    str(p["volume"]),
                    f"{p['open_price']:.2f}",
                    f"{p['sl']:.2f}",
                    f"{p['tp']:.2f}",
                    Text(f"{p['profit']:.2f}", style=profit_style),
                )

        event_lines = list(self.events) if self.events else [Text("Waiting for activity...", style="dim")]
        events_panel = Panel(Group(*event_lines), title="Recent Events")

        return Group(header, pos_table, events_panel)
